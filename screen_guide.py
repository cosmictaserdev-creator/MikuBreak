import os
import re

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from brain.llm_client import LLMClient
from voice.tts import get_speaker
from voice.player import SpeechPlayer
from stt.groq_whisper import PushToTalk, WhisperTranscriber
from screen.capture import get_foreground_window_title, get_ui_elements, format_ui_elements, capture_screenshot
from screen_overlay import PointMarker
from chat_controller import _read_duration_ms

POINT_NUM = r"-?\d+(?:\.\d+)?"
POINT_TAG_RE = re.compile(rf"\[POINT:\s*({POINT_NUM})\s*,\s*({POINT_NUM})\s*:\s*([^\]]+)\]")


def _is_blocked(title, blocklist):
    title_lower = (title or "").lower()
    return any(term.lower() in title_lower for term in (blocklist or []))


class ScreenGuideWorker(QThread):
    """Transcribe -> capture context -> ask -> synth, all off the GUI thread."""

    succeeded = pyqtSignal(str, object, str, str)  # answer (tag stripped), (x,y) or None, audio path, screenshot path
    failed = pyqtSignal(str)

    def __init__(self, llm_client, transcriber, speaker, audio):
        super().__init__()
        self.llm_client = llm_client
        self.transcriber = transcriber
        self.speaker = speaker
        self.audio = audio

    def run(self):
        try:
            question = self.transcriber.transcribe(self.audio)
        except Exception as e:
            self.failed.emit(f"Couldn't hear that clearly. ({e})")
            return
        finally:
            if isinstance(self.audio, str):
                try:
                    os.remove(self.audio)
                except OSError:
                    pass

        if not question.strip():
            self.failed.emit("Didn't catch anything.")
            return

        title = get_foreground_window_title()
        if _is_blocked(title, self.llm_client.config.get("screen_guide_blocklist")):
            self.failed.emit("That window's private, I'll skip looking there.")
            return

        # Always send both: the element list gives exact coordinates, the screenshot
        # gives the vision model the actual pixels (icons, images, layout).
        elements = get_ui_elements()
        ui_context = format_ui_elements(elements)
        image_path = capture_screenshot()

        try:
            answer = self.llm_client.ask_screen(question, ui_context, image_path)
        except Exception as e:
            self.failed.emit(f"Ngh... couldn't look just now. ({e})")
            if image_path:
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            return
        # screenshot survives to become the chat thumbnail; controller deletes it after display

        point = None
        text = answer
        match = POINT_TAG_RE.search(answer)
        if match:
            point = (int(float(match.group(1))), int(float(match.group(2))))
            text = (answer[:match.start()] + answer[match.end():]).strip()

        # Shares conversation_log with regular chat so both surfaces build the same
        # picture of the user over time (Miku's own memory tools can recall this later).
        self.llm_client.store.log_conversation("user", f"[screen] {question}")
        self.llm_client.store.log_conversation("assistant", text)

        audio_path = ""
        if not self.speaker.config.get("muted"):
            try:
                audio_path = self.speaker.speak(text)
            except Exception:
                pass

        self.succeeded.emit(text, point, audio_path, image_path or "")


class ScreenGuideController(QObject):
    """Push-to-talk (separate hotkey from chat) -> screen capture -> answer + walk-and-point."""

    def __init__(self, config, mascot, store, pill, chat_controller=None):
        super().__init__()
        self.config = config
        self.mascot = mascot
        self.pill = pill
        self.llm_client = LLMClient(config, store)
        self.transcriber = WhisperTranscriber(config)
        self._chat_controller = chat_controller

        self.marker = PointMarker()

        self.speech = SpeechPlayer(config)
        self.speech.finished.connect(self._finish_talking)

        self._worker = None
        self._skip_next = False

        self.push_to_talk = PushToTalk(config.get("screen_guide_hotkey"), config)
        self.push_to_talk.started.connect(self._on_started)
        self.push_to_talk.amplitude.connect(self.pill.update_amplitude)
        self.push_to_talk.finished.connect(self._on_recorded)
        self.push_to_talk.start()

    def _on_started(self):
        if not self.config.get("screen_guide_enabled"):
            self._skip_next = True
            self.push_to_talk.recorder.stop()  # discard, skill is disabled
            return
        self.mascot.reset_roaming()
        self.mascot.set_state("wondering_right")  # "listening"
        self.pill.start_listening()

    def _on_recorded(self, wav_path):
        if self._skip_next:
            self._skip_next = False
            if wav_path and isinstance(wav_path, str):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            return
        if not wav_path:
            self.mascot.set_state("idle")
            self.pill.return_to_idle()
            self.pill.show_response("I couldn't hear anything — check your mic in Settings.")
            return
        self.pill.start_thinking()
        speaker = get_speaker(self.config)
        self._worker = ScreenGuideWorker(self.llm_client, self.transcriber, speaker, wav_path)
        self._worker.succeeded.connect(self._on_answer)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_answer(self, text, point, audio_path, image_path):
        if self._chat_controller:
            self._chat_controller.sync_external_turn("user", text)
        if point:
            x, y = point
            target_x = x - self.mascot.width() // 2
            self.mascot.walk_to(target_x, lambda: self._say(text, audio_path, x, y, image_path), speed=8, state="run")
        else:
            self._say(text, audio_path, None, None, image_path)

    def _on_failed(self, message):
        self._say(message, "", None, None, "")

    def _say(self, text, audio_path, point_x, point_y, image_path=""):
        self.mascot.set_state("dialog")
        if point_x is not None:
            self.marker.show_at(point_x, point_y, label=text[:40])

        if image_path:
            self.pill.show_screen_response(text, image_path)  # loads pixmap immediately
            try:
                os.remove(image_path)
            except OSError:
                pass
        else:
            self.pill.show_response(text)

        if audio_path:
            self.speech.play(audio_path)
        else:
            QTimer.singleShot(_read_duration_ms(text), self._finish_talking)

    def _finish_talking(self):
        self.mascot.set_state("idle")
        self.pill.return_to_idle()

    def stop(self):
        self.push_to_talk.stop()
