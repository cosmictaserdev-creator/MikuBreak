import os
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import QMessageBox

from brain.llm_client import LLMClient
from voice.tts import get_speaker
from stt.groq_whisper import PushToTalk, WhisperTranscriber
from audio_devices import apply_output_device
from hotkeys import HotkeyPoller
from focus_mode import FocusMode

HISTORY_SEED_TURNS = 40  # conversation_log rows loaded as history on startup
SUMMARIZE_THRESHOLD = 80  # conversation_log rows before we summarize the oldest chunk
SUMMARIZE_CHUNK = 40


def _read_duration_ms(text: str) -> int:
    """Rough reading-time heuristic for how long the response panel should stay up."""
    return max(3000, min(12000, len(text) * 60))


class AskWorker(QThread):
    """Runs the (blocking) LLM call + TTS synth off the GUI thread."""

    succeeded = pyqtSignal(str, str)  # reply text, audio path ("" if TTS failed)
    failed = pyqtSignal(str)
    chunk = pyqtSignal(str)  # live streamed text as it generates
    stream_reset = pyqtSignal()  # streamed text was a tool-call turn — discard it

    def __init__(self, llm_client, speaker, prompt, history):
        super().__init__()
        self.llm_client = llm_client
        self.speaker = speaker
        self.prompt = prompt
        self.history = history

    def run(self):
        try:
            reply = self.llm_client.ask(
                self.prompt, self.history,
                on_delta=self.chunk.emit,
                on_reset=self.stream_reset.emit,
            )
        except Exception as e:
            self.failed.emit(f"Ngh... I couldn't think just now. ({e})")
            return

        audio_path = ""
        if not self.speaker.config.get("muted"):
            try:
                audio_path = self.speaker.speak(reply)
            except Exception:
                pass  # text-only fallback

        self.succeeded.emit(reply, audio_path)


class SpeakWorker(QThread):
    """Synthesizes speech for text that's already decided (nudges, chatter) — no LLM call."""

    ready = pyqtSignal(str, str)  # text, audio path ("" if TTS failed)

    def __init__(self, speaker, text):
        super().__init__()
        self.speaker = speaker
        self.text = text

    def run(self):
        path = ""
        if not self.speaker.config.get("muted"):
            try:
                path = self.speaker.speak(self.text)
            except Exception:
                pass
        self.ready.emit(self.text, path)


class TranscribeWorker(QThread):
    """Push-to-talk voice chat: Whisper transcription off the GUI thread."""

    transcribed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, transcriber, wav_path):
        super().__init__()
        self.transcriber = transcriber
        self.wav_path = wav_path

    def run(self):
        try:
            text = self.transcriber.transcribe(self.wav_path)
        except Exception as e:
            self.failed.emit(f"Couldn't hear that clearly. ({e})")
            return
        finally:
            try:
                os.remove(self.wav_path)
            except OSError:
                pass

        if not text.strip():
            self.failed.emit("Didn't catch anything.")
            return
        self.transcribed.emit(text)


class ImageAskWorker(QThread):
    """Vision call for a dropped image, off the GUI thread."""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, llm_client, question, image_path):
        super().__init__()
        self.llm_client = llm_client
        self.question = question
        self.image_path = image_path

    def run(self):
        try:
            self.succeeded.emit(self.llm_client.ask_screen(self.question, "", self.image_path))
        except Exception as e:
            self.failed.emit(f"Couldn't look at that image. ({e})")


class SummarizeWorker(QThread):
    """Folds the oldest chunk of conversation_log into one memory, off the GUI thread.
    Best-effort — a failure here should never disrupt the chat itself."""

    def __init__(self, llm_client, store, rows):
        super().__init__()
        self.llm_client = llm_client
        self.store = store
        self.rows = rows

    def run(self):
        try:
            transcript = "\n".join(f"{r['role']}: {r['content']}" for r in self.rows)
            summary = self.llm_client.summarize_conversation(transcript)
            self.store.add_memory("conversation_summary", summary, importance=2, source="auto")
            self.store.delete_conversation_up_to(self.rows[-1]["id"])
        except Exception:
            pass


class ChatController(QObject):
    """Hotkey -> text/voice input -> LLM -> floating pill (waveform -> chat panel) + voice."""

    MAX_HISTORY_TURNS = 20

    _timer_create_requested = pyqtSignal(int, str)
    _timer_cancel_requested = pyqtSignal(int)
    _confirm_requested = pyqtSignal(str, object)
    _focus_start_requested = pyqtSignal(int)
    _focus_end_requested = pyqtSignal()

    def __init__(self, config, mascot, store, pill):
        super().__init__()
        self.config = config
        self.mascot = mascot
        self.store = store
        self.pill = pill

        # Tool callbacks. set_timer/confirm run on worker threads, so they marshal
        # to the GUI thread via queued signals.
        self._timers = {}  # id -> {"label", "qtimer", "end"}
        self._timer_seq = 0
        self._timer_create_requested.connect(self._create_timer)
        self._timer_cancel_requested.connect(self._cancel_timer_gui)
        self._confirm_requested.connect(self._on_confirm_requested)

        self.focus = FocusMode(config, self)
        self._focus_start_requested.connect(self.focus.start)
        self._focus_end_requested.connect(lambda: self.focus.end(early=True))

        actions = SimpleNamespace(
            set_timer=lambda seconds, label: self._timer_create_requested.emit(seconds, label),
            list_timers=self.list_timers,
            cancel_timer=self.cancel_timer,
            confirm_command=self._confirm_command,
            start_focus=self._start_focus,
            end_focus=self._end_focus,
            focus_status=lambda: self.focus.status(),
        )

        self.llm_client = LLMClient(config, store, actions)
        self.history = self._load_history()

        self.pill.submitted.connect(self.handle_prompt)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        apply_output_device(self.audio_output, config)
        self.player.setAudioOutput(self.audio_output)

        self._worker = None
        self._nudge_worker = None
        self._transcribe_worker = None
        self._summarize_worker = None
        self._active_nudge_text = None

        self._hotkey = HotkeyPoller(self.config.get("chat_hotkey"))
        self._hotkey.pressed.connect(self._show_input)
        self._hotkey.start()

        self.transcriber = WhisperTranscriber(config)
        self.voice_ptt = PushToTalk(config.get("voice_chat_hotkey"), config)
        self.voice_ptt.started.connect(self._on_voice_started)
        self.voice_ptt.amplitude.connect(self.pill.update_amplitude)
        self.voice_ptt.finished.connect(self._on_voice_recorded)
        self.voice_ptt.start()

    # -- timers (created on the GUI thread; tools call in via queued signal) --------

    def _create_timer(self, duration_seconds, label):
        self._timer_seq += 1
        timer_id = self._timer_seq
        qtimer = QTimer(self)
        qtimer.setSingleShot(True)
        qtimer.timeout.connect(lambda: self._on_timer_fired(timer_id))
        qtimer.start(duration_seconds * 1000)
        self._timers[timer_id] = {
            "label": label,
            "qtimer": qtimer,
            "end": datetime.now() + timedelta(seconds=duration_seconds),
        }

    def _on_timer_fired(self, timer_id):
        entry = self._timers.pop(timer_id, None)
        if entry:
            self._speak_nudge(f"Hey! {entry['label']} is ready!")

    def list_timers(self):
        """Called from the LLM worker thread — pure reads, safe."""
        now = datetime.now()
        return [
            {"label": t["label"], "remaining_seconds": max(0, int((t["end"] - now).total_seconds()))}
            for t in self._timers.values()
        ]

    def cancel_timer(self, label):
        """Called from the LLM worker thread; QTimer.stop must happen on the GUI thread."""
        for timer_id, t in list(self._timers.items()):
            if t["label"].lower() == label.lower():
                self._timer_cancel_requested.emit(timer_id)
                return f"cancelled timer '{t['label']}'"
        return f"no timer named '{label}'"

    def _cancel_timer_gui(self, timer_id):
        entry = self._timers.pop(timer_id, None)
        if entry:
            entry["qtimer"].stop()

    # -- focus mode (tool callbacks run on the worker thread; marshal via signals) ----

    def _start_focus(self, minutes):
        if self.focus.active:
            return "a focus session is already running — end it first"
        self._focus_start_requested.emit(minutes)
        return f"focus session started for {minutes} minutes"

    def _end_focus(self):
        if not self.focus.active:
            return "no focus session running"
        self._focus_end_requested.emit()
        return "focus session ended"

    # -- confirm-to-run shell --------------------------------------------------------

    def _confirm_command(self, command):
        """Called from the LLM worker thread. Blocks until the user answers (or 60s)."""
        event = threading.Event()
        holder = {"approved": False}
        self._confirm_requested.emit(command, (event, holder))
        event.wait(60)
        return holder["approved"]

    def _on_confirm_requested(self, command, payload):
        event, holder = payload
        result = QMessageBox.question(
            None,
            "Miku wants to run a command",
            f"Allow Miku to run this command?\n\n{command}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        holder["approved"] = result == QMessageBox.StandardButton.Yes
        event.set()

    def _load_history(self):
        rows = self.store.get_recent_conversation(limit=HISTORY_SEED_TURNS)
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def _show_input(self):
        self.mascot.reset_roaming()
        self.pill.open_chat()

    def _on_voice_started(self):
        self.mascot.reset_roaming()
        self.mascot.set_state("wondering_right")  # "listening"
        self.pill.start_listening()

    def _on_voice_recorded(self, wav_path):
        if not wav_path:
            self.mascot.set_state("idle")
            self.pill.return_to_idle()
            self.pill.show_response("I couldn't hear anything — check your mic in Settings.")
            return
        self.pill.start_thinking()
        self._transcribe_worker = TranscribeWorker(self.transcriber, wav_path)
        self._transcribe_worker.transcribed.connect(self._on_voice_text)
        self._transcribe_worker.failed.connect(self._on_failed)
        self._transcribe_worker.start()

    def _on_voice_text(self, text):
        self.pill.add_user_message(text)  # voice turns land in the chat thread too
        self.handle_prompt(text)

    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    def handle_file_drop(self, path):
        """File dropped from Explorer onto the mascot: images go to the vision model,
        text files get summarized in chat, anything else is declined."""
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        self.mascot.reset_roaming()

        if ext in self.IMAGE_EXTS:
            self.pill.add_user_message(f"🖼 {name}")
            self.pill.start_thinking()
            self.mascot.set_state("wondering_left")
            self._file_worker = ImageAskWorker(
                self.llm_client,
                "The user dropped this image on you. Describe what it shows, briefly and warmly.",
                path,
            )
            self._file_worker.succeeded.connect(self._speak_nudge)
            self._file_worker.failed.connect(self._on_failed)
            self._file_worker.start()
            return

        from brain.tools import _read_text_file
        content = _read_text_file(path)
        # binary sniff: errors="replace" turns undecodable bytes into U+FFFD
        if content.startswith(("file not found", "couldn't read")) or \
                content.count("�") > max(4, len(content) // 20):
            self._say(f"Hmm, I can't read {name} — I only understand text files and images for now.", "")
            return

        self.pill.add_user_message(f"📄 {name}")
        self.handle_prompt(
            f"The user dropped the file '{name}' on you. Contents:\n---\n{content}\n---\n"
            "Summarize it briefly, then offer to answer questions about it."
        )

    def handle_prompt(self, text):
        self.mascot.set_state("wondering_left")  # "thinking"
        self.pill.start_thinking()
        speaker = get_speaker(self.config)
        history = self.history[-self.MAX_HISTORY_TURNS * 2:]

        self._worker = AskWorker(self.llm_client, speaker, text, history)
        self._worker.succeeded.connect(lambda reply, path: self._on_reply(text, reply, path))
        self._worker.failed.connect(self._on_failed)
        self._worker.chunk.connect(self.pill.stream_delta)
        self._worker.stream_reset.connect(self.pill.reset_stream)
        self._worker.start()

    def _on_reply(self, prompt, reply, audio_path):
        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": reply})
        self.store.log_conversation("user", prompt)
        self.store.log_conversation("assistant", reply)
        self._maybe_summarize()
        self._say(reply, audio_path)

    def sync_external_turn(self, role, content):
        """Receive a conversation turn from an external source (screen guide, etc.)
        so the in-memory history stays coherent."""
        self.history.append({"role": role, "content": content})

    def _maybe_summarize(self):
        if self.store.count_conversation() < SUMMARIZE_THRESHOLD:
            return
        rows = self.store.get_oldest_conversation(SUMMARIZE_CHUNK)
        self._summarize_worker = SummarizeWorker(self.llm_client, self.store, rows)
        self._summarize_worker.start()

    def _on_failed(self, message):
        self._say(message, "")

    def deliver_nudge(self, text):
        """Unprompted delivery — reminders/habits/chatter. Walks to a visible spot first."""
        if self.mascot.dragging:
            return
        self._active_nudge_text = text
        screen = self.mascot.screen().availableGeometry()
        target_x = (screen.width() - self.mascot.width()) // 2
        self.mascot.reset_roaming()
        self.mascot.walk_to(target_x, lambda: self._speak_nudge(text), speed=6, state="walk")

    def interrupt(self):
        """Shake-to-pause: stop whatever she's doing right now. Returns the text of a
        reminder/habit nudge that got cut off mid-delivery, or None if it wasn't a nudge."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        interrupted = self._active_nudge_text
        self._active_nudge_text = None
        self.pill.return_to_idle()
        return interrupted

    def _speak_nudge(self, text):
        speaker = get_speaker(self.config)
        self._nudge_worker = SpeakWorker(speaker, text)
        self._nudge_worker.ready.connect(self._say)
        self._nudge_worker.start()

    def _say(self, text, audio_path):
        self.mascot.set_state("dialog")  # "talking"
        self.pill.show_response(text)

        if audio_path:
            cleanup = self._make_cleanup(audio_path)
            self.player.mediaStatusChanged.connect(cleanup)
            self.player.setSource(QUrl.fromLocalFile(audio_path))
            self.player.play()
        else:
            QTimer.singleShot(_read_duration_ms(text), self._finish_talking)

    def _finish_talking(self):
        self._active_nudge_text = None
        self.mascot.set_state("idle")
        self.pill.return_to_idle()

    def _make_cleanup(self, path):
        def cleanup(status):
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.mediaStatusChanged.disconnect(cleanup)
                self.player.stop()
                try:
                    os.remove(path)
                except OSError:
                    pass
                self._finish_talking()
        return cleanup

    def stop(self):
        self._hotkey.stop()
        self.voice_ptt.stop()
