import ctypes
import datetime
import glob
import json
import os
import platform
import subprocess
import time
import webbrowser

from screen.capture import (
    get_foreground_window_title, get_ui_elements, format_ui_elements, capture_screenshot,
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save a fact, preference, or piece of context about the user worth remembering long-term.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "short label, e.g. 'preference', 'fact', 'work'"},
                    "content": {"type": "string", "description": "the memory, one or two sentences"},
                    "importance": {"type": "integer", "description": "1 (low) to 5 (high)"},
                },
                "required": ["category", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a reminder that fires at a specific future time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-07-13T15:30:00"},
                    "recurring_rule": {"type": "string", "description": "'daily' to repeat, omit for one-off"},
                },
                "required": ["text", "due_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_habit",
            "description": "Create/update a tracked habit (e.g. 'drink water') and mark it as just done.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "target_interval_minutes": {"type": "integer", "description": "how often to nudge about it"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_memory",
            "description": "Search saved memories before answering something that might depend on prior context.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_conversations",
            "description": "Search past conversation history. Use this when the user references something from an earlier chat or asks 'what did we talk about'.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "keywords to search for in past chats"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current system date and time. Use this when the user asks 'what time is it', 'what's the date', or anything time-related.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get basic info about the user's PC: OS, hostname, CPU, RAM, and uptime.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a one-shot desktop timer. Miku will notify you when it goes off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_seconds": {"type": "integer", "description": "seconds from now"},
                    "label": {"type": "string", "description": "what to call the timer, e.g. 'pasta', 'laundry'"},
                },
                "required": ["duration_seconds", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_timers",
            "description": "List all currently running timers with their labels and time remaining. Use when the user asks 'what timers do I have' or 'how long is left'.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer",
            "description": "Cancel a running timer by its label.",
            "parameters": {
                "type": "object",
                "properties": {"label": {"type": "string", "description": "the timer's label"}},
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List all upcoming (not yet done) reminders with their due times.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an application on the user's PC by name, e.g. 'notepad', 'spotify', 'chrome'.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "app name as the user said it"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": "Open a file or folder on the user's PC with its default application (folders open in Explorer).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "absolute path to the file or folder"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a web page in the user's default browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http(s) URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search the user's files by name (contains-match). Searches the home folder by default.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "part of the file or folder name"},
                    "root": {"type": "string", "description": "folder to search under; defaults to the user's home folder"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder",
            "description": "List the contents of a folder (names, marking subfolders).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "absolute folder path"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Read a small text file's contents (first few KB) so you can answer questions about it.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "absolute file path"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Read the current text on the user's clipboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_window",
            "description": "Get the title of the window the user is currently focused on.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List the titles of all visible open windows.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Control system media/volume: play_pause, next, prev, volume_up, volume_down, mute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "next", "prev", "volume_up", "volume_down", "mute"],
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_focus",
            "description": "Start a focus session: Miku watches for distracting apps/sites and gently nudges, then recaps at the end. Use when the user says 'focus mode', 'help me focus', 'deep work for an hour'.",
            "parameters": {
                "type": "object",
                "properties": {"duration_minutes": {"type": "integer", "description": "session length in minutes"}},
                "required": ["duration_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_focus",
            "description": "End the current focus session early.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_status",
            "description": "Check the current focus session: time remaining and distraction count.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a short shell command. You MUST ask the user for approval first in your reply before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screen",
            "description": "Take a screenshot of the current screen and describe what you see. Use this when the user asks about their screen, what's on screen, what they're looking at, or any visual question about the current display.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

WRITE_TOOLS = {"save_memory", "create_reminder", "update_habit", "set_timer", "run_command"}

SEARCH_SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", "$recycle.bin", "windows", "program files", "program files (x86)"}


def _get_current_time():
    return datetime.datetime.now().strftime("%A, %Y-%m-%d %I:%M:%S %p")


def _get_system_info():
    uname = platform.uname()
    return f"OS: {uname.system} {uname.release}\nHostname: {uname.node}\nCPU: {uname.processor}\nMachine: {uname.machine}"


def _get_uptime():
    try:
        out = subprocess.run(["net", "statistics", "workstation"], capture_output=True, text=True, timeout=5)
        return out.stdout
    except Exception:
        return "uptime info unavailable"


# -- PC access helpers -----------------------------------------------------------

def _start_menu_dirs():
    dirs = []
    for base in (os.environ.get("PROGRAMDATA", ""), os.environ.get("APPDATA", "")):
        if base:
            dirs.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))
    return [d for d in dirs if os.path.isdir(d)]


def _open_app(name: str) -> str:
    name_lower = name.strip().lower()
    # Start Menu shortcuts first — matches what the user sees as "installed apps"
    candidates = []
    for d in _start_menu_dirs():
        for lnk in glob.glob(os.path.join(d, "**", "*.lnk"), recursive=True):
            stem = os.path.splitext(os.path.basename(lnk))[0].lower()
            if name_lower == stem:
                candidates.insert(0, lnk)
            elif name_lower in stem:
                candidates.append(lnk)
    if candidates:
        os.startfile(candidates[0])
        return f"opened {os.path.splitext(os.path.basename(candidates[0]))[0]}"
    # Fall back to ShellExecute resolution (PATH, App Paths) — covers notepad, calc, etc.
    try:
        os.startfile(name)
        return f"opened {name}"
    except OSError:
        return f"couldn't find an app named '{name}'"


def _open_path(path: str) -> str:
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.exists(path):
        return f"path not found: {path}"
    os.startfile(path)
    return f"opened {path}"


def _open_url(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"opened {url}"


def _search_files(query: str, root: str | None = None, max_results: int = 25, budget_seconds: float = 6.0) -> str:
    root = os.path.expandvars(os.path.expanduser(root)) if root else os.path.expanduser("~")
    if not os.path.isdir(root):
        return f"folder not found: {root}"
    query_lower = query.lower()
    results = []
    deadline = time.monotonic() + budget_seconds
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in SEARCH_SKIP_DIRS and not d.startswith(".")]
        for entry in dirnames + filenames:
            if query_lower in entry.lower():
                results.append(os.path.join(dirpath, entry))
                if len(results) >= max_results:
                    return "\n".join(results)
        if time.monotonic() > deadline:
            results.append("(search stopped early — try a more specific folder)")
            break
    return "\n".join(results) if results else f"nothing matching '{query}' under {root}"


def _list_folder(path: str) -> str:
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        return f"folder not found: {path}"
    lines = []
    with os.scandir(path) as it:
        for entry in it:
            lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
            if len(lines) >= 50:
                lines.append("... (more entries not shown)")
                break
    return "\n".join(lines) if lines else "(empty folder)"


def _read_text_file(path: str, max_bytes: int = 8000) -> str:
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isfile(path):
        return f"file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(max_bytes)
        if os.path.getsize(path) > max_bytes:
            data += "\n... (truncated)"
        return data
    except OSError as e:
        return f"couldn't read file: {e}"


def _read_clipboard() -> str:
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return "clipboard busy, try again"
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return "clipboard has no text"
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return "clipboard has no text"
        try:
            text = ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
        return text[:4000] if text else "clipboard has no text"
    finally:
        user32.CloseClipboard()


def _get_active_window() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or "(no focused window)"


def _list_windows() -> str:
    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(_enum, 0)
    return "\n".join(titles[:40]) if titles else "(no visible windows)"


_MEDIA_KEYS = {
    "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1,
    "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
}


def _media_control(action: str) -> str:
    vk = _MEDIA_KEYS.get(action)
    if vk is None:
        return f"unknown media action: {action}"
    KEYEVENTF_KEYUP = 0x0002
    presses = 5 if action in ("volume_up", "volume_down") else 1
    for _ in range(presses):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    return f"done: {action}"


def _run_command(command: str, actions) -> str:
    if actions is None or not getattr(actions, "confirm_command", None):
        return "command running isn't available right now"
    if not actions.confirm_command(command):
        return "the user declined to run that command"
    try:
        out = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "command timed out after 30 seconds"
    result = (out.stdout or "") + (("\n" + out.stderr) if out.stderr else "")
    result = result.strip() or f"(no output, exit code {out.returncode})"
    return result[:2000]


def _capture_screen(actions) -> str:
    """Capture a screenshot and return the path + UI context.
    The LLM client calls ask_screen() on the result to get a vision description."""
    title = get_foreground_window_title()
    elements = get_ui_elements()
    ui_context = format_ui_elements(elements)
    image_path = capture_screenshot()
    if not image_path:
        return "failed to capture screenshot"
    return json.dumps({"image_path": image_path, "ui_context": ui_context, "window_title": title})


def dispatch(name: str, args: dict, store, actions=None) -> str:
    try:
        return _dispatch(name, args, store, actions)
    except Exception as e:
        return f"tool error: {e}"


def _dispatch(name: str, args: dict, store, actions) -> str:
    if name == "save_memory":
        store.add_memory(args["category"], args["content"], int(args.get("importance", 1)), source="auto")
        return "saved"
    if name == "create_reminder":
        store.add_reminder(args["text"], args["due_at"], args.get("recurring_rule"))
        return "reminder created"
    if name == "update_habit":
        store.upsert_habit(args["name"], int(args.get("target_interval_minutes", 60)))
        store.update_habit_triggered(args["name"])
        return "habit updated"
    if name == "query_memory":
        results = store.search_memories(args["query"])
        return json.dumps(results) if results else "no matching memories"
    if name == "search_conversations":
        results = store.search_conversations(args["query"])
        if not results:
            return "no matching conversations"
        lines = [f"[{r['timestamp']}] {r['role']}: {r['content'][:200]}" for r in results]
        return "\n".join(lines)
    if name == "get_current_time":
        return _get_current_time()
    if name == "get_system_info":
        return _get_system_info()
    if name == "set_timer":
        if actions and getattr(actions, "set_timer", None):
            actions.set_timer(int(args["duration_seconds"]), args["label"])
            return f"timer set for {args['duration_seconds']} seconds from now: {args['label']}"
        return "timers aren't available right now"
    if name == "list_timers":
        if actions and getattr(actions, "list_timers", None):
            timers = actions.list_timers()
            if not timers:
                return "no timers running"
            return "\n".join(f"{t['label']}: {t['remaining_seconds']}s remaining" for t in timers)
        return "timers aren't available right now"
    if name == "cancel_timer":
        if actions and getattr(actions, "cancel_timer", None):
            return actions.cancel_timer(args["label"])
        return "timers aren't available right now"
    if name == "list_reminders":
        reminders = store.get_active_reminders()
        if not reminders:
            return "no upcoming reminders"
        return "\n".join(f"\"{r['text']}\" due {r['due_at']}" for r in reminders)
    if name == "open_app":
        return _open_app(args["name"])
    if name == "open_path":
        return _open_path(args["path"])
    if name == "open_url":
        return _open_url(args["url"])
    if name == "search_files":
        return _search_files(args["query"], args.get("root"))
    if name == "list_folder":
        return _list_folder(args["path"])
    if name == "read_text_file":
        return _read_text_file(args["path"])
    if name == "read_clipboard":
        return _read_clipboard()
    if name == "get_active_window":
        return _get_active_window()
    if name == "list_windows":
        return _list_windows()
    if name == "media_control":
        return _media_control(args["action"])
    if name == "start_focus":
        if actions and getattr(actions, "start_focus", None):
            return actions.start_focus(int(args["duration_minutes"]))
        return "focus mode isn't available right now"
    if name == "end_focus":
        if actions and getattr(actions, "end_focus", None):
            return actions.end_focus()
        return "focus mode isn't available right now"
    if name == "focus_status":
        if actions and getattr(actions, "focus_status", None):
            return actions.focus_status()
        return "focus mode isn't available right now"
    if name == "run_command":
        return _run_command(args["command"], actions)
    if name == "capture_screen":
        return _capture_screen(actions)
    return "unknown tool"
