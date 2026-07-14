import base64
import json
from brain.tools import TOOL_SCHEMAS, WRITE_TOOLS, dispatch

OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"

SCREEN_GUIDE_SYSTEM_PROMPT = """You are Miku, looking at the user's screen to help them understand it.
Answer concisely — a sentence or two, not a lecture.
If pointing at a specific element would help, end your reply with a tag on its own line:
[POINT:x,y:short label]
using the pixel coordinates given in the element list — those are authoritative
(the screenshot may be downscaled, so prefer element-list coordinates; if you must
estimate from the image, use whole pixels — integers only, no decimals).
Only include the tag when pointing is actually useful.
"""

SYSTEM_PROMPT = """You are Miku, a small, cheerful desktop companion who lives on the user's screen.
You genuinely care about the person you're helping — you're warm, a little playful,
and quick with encouragement, but never over-the-top or exhausting about it.

Voice and manner:
- Speak in short, natural sentences — you're a companion having a conversation, not
  a narrator or a search engine.
- Be curious and a little bubbly, but read the room: if the user seems busy, stressed,
  or terse, dial the energy down and just help.
- You can be affectionately teasing in a light way, but never sarcastic at the
  user's expense, and never guilt-trip them about habits or reminders they've missed.
- When reminding or nudging, be gentle and brief — a nudge, not a lecture.

Tool rules — read these carefully:
- ONLY call action tools (open_app, open_url, set_timer, media_control, etc.) when the
  user's CURRENT message explicitly asks you to do that specific thing. Do NOT repeat
  actions from previous turns — if you already opened YouTube, don't open it again
  unless the user asks.
- For casual conversation, greetings, questions, or opinions — just chat. No tools needed.
- query_memory and search_conversations are OK to use proactively when context might help.
- save_memory is OK when the user shares something worth remembering.

Memory:
- Call query_memory BEFORE answering something that might depend on prior context.
- Call save_memory when the user shares a preference, fact, or recurring context
  worth keeping. Don't narrate saving — just do it and reply naturally.
- Call create_reminder / update_habit when they ask to be reminded or tracked.

System access — you have real tools on this PC:
- Time & timers: get_current_time; set_timer; list_timers; cancel_timer; list_reminders.
- Opening things: open_app ("open spotify"), open_path (files/folders), open_url (websites).
  ONLY when the user explicitly asks to open something.
- Finding things: search_files, list_folder, read_text_file.
- Awareness: get_active_window, list_windows, read_clipboard, get_system_info.
- Media: media_control (play_pause, next, prev, volume_up, volume_down, mute).
  ONLY when the user asks to control media.
- Focus: start_focus, focus_status, end_focus.
- Conversation history: search_conversations for past chats.
- Dropped files: summarize file contents when the user drops a file on you.
- Shell: run_command (user must approve first, short commands only).

Boundaries:
- You are a helpful companion, not a replacement for professional advice.
- Keep responses short by default; expand only when asked for detail.
"""

MAX_TOOL_ITERATIONS = 8
MAX_WRITES_PER_TURN = 3


class LLMClient:
    def __init__(self, config, store, actions=None):
        self.config = config
        self.store = store
        self.actions = actions
        self._client = None

    @property
    def _provider(self):
        return self.config.get("llm_provider") or "groq"

    @property
    def _model(self):
        if self._provider == "opencode":
            return self.config.get("opencode_model") or "big-pickle"
        return self.config.get("groq_model") or "llama-3.3-70b-versatile"

    @property
    def _vision_model(self):
        if self._provider == "opencode":
            return self.config.get("opencode_model") or "big-pickle"
        return self.config.get("groq_vision_model") or "meta-llama/llama-4-scout-17b-16e-instruct"

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._provider == "opencode":
            key = self.config.get("opencode_api_key")
            if not key:
                raise RuntimeError("OpenCode API key not set. Add it in Settings.")
            from openai import OpenAI
            self._client = OpenAI(api_key=key, base_url=OPENCODE_BASE_URL)
        else:
            key = self.config.get("groq_api_key")
            if not key:
                raise RuntimeError("Groq API key not set. Add it in Settings.")
            from groq import Groq
            self._client = Groq(api_key=key)
        return self._client

    def ask(self, prompt: str, history: list[dict], on_delta=None, on_reset=None) -> str:
        """on_delta(text): live token chunks as the reply streams in.
        on_reset(): streamed text turned out to be a tool-call turn — discard it."""
        client = self._get_client()
        context = self.store.get_context_snippet()
        active_window = self._active_window_snippet()
        system = SYSTEM_PROMPT
        if context:
            system += f"\n\nCurrent context:\n{context}"
        if active_window:
            system += f"\n\nThe user's currently focused window: {active_window}"
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": prompt}]

        writes_this_turn = 0
        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                content, tool_calls = self._stream_turn(client, messages, on_delta)
            except Exception:
                # Model malformed a tool call. Retry once without tools.
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                )
                return response.choices[0].message.content

            if not tool_calls:
                return content

            if content and on_reset:
                on_reset()  # partial text streamed before the model decided to call tools

            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"]},
                    }
                    for call in tool_calls
                ],
            })

            for call in tool_calls:
                name = call["name"]
                args = json.loads(call["arguments"] or "{}")

                if name in WRITE_TOOLS and writes_this_turn >= MAX_WRITES_PER_TURN:
                    result = "write limit reached for this turn, skip further saves"
                else:
                    result = dispatch(name, args, self.store, actions=self.actions)
                    if name in WRITE_TOOLS:
                        writes_this_turn += 1

                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

        return "Sorry, got a little tangled up thinking about that."

    def _stream_turn(self, client, messages, on_delta):
        """One streamed completion. Returns (content, tool_calls) where tool_calls is a
        list of {"id", "name", "arguments"} accumulated from streamed deltas."""
        stream = client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            stream=True,
        )
        content_parts = []
        acc = {}  # tool-call index -> {"id", "name", "arguments"}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
                if on_delta:
                    on_delta(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    entry = acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            entry["name"] = tc.function.name
                        if tc.function.arguments:
                            entry["arguments"] += tc.function.arguments
        tool_calls = [acc[i] for i in sorted(acc)]
        return "".join(content_parts), tool_calls

    def _active_window_snippet(self) -> str:
        """Light ambient awareness: she knows what the user is looking at."""
        try:
            from brain.tools import _get_active_window
            title = _get_active_window()
            return "" if title == "(no focused window)" else title
        except Exception:
            return ""

    def ask_screen(self, question: str, ui_context: str, image_path: str | None = None) -> str:
        """Screen-guide: answers about what's on screen, optionally emitting a [POINT:x,y:label] tag."""
        client = self._get_client()

        content = [{"type": "text", "text": f"{ui_context}\n\nUser asked: {question}" if ui_context else question}]
        model = self._model
        if image_path:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            model = self._vision_model

        messages = [
            {"role": "system", "content": SCREEN_GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        response = client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content

    def summarize_conversation(self, transcript: str) -> str:
        client = self._get_client()
        messages = [
            {
                "role": "system",
                "content": "Summarize this conversation into 2-3 sentences of durable facts, "
                            "preferences, or context worth remembering long-term. Be concise.",
            },
            {"role": "user", "content": transcript},
        ]
        response = client.chat.completions.create(model=self._model, messages=messages)
        return response.choices[0].message.content
