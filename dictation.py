import ctypes
import os
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

from stt.groq_whisper import PushToTalk, WhisperTranscriber

KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


def _win_paste(text: str):
    """Set clipboard and simulate Ctrl+V using Win32 keybd_event — more reliable than
    pynput's Controller on Windows, where scan-code events often get swallowed."""
    clipboard = QApplication.clipboard()
    previous = clipboard.text()
    clipboard.setText(text)

    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    QTimer.singleShot(500, lambda: clipboard.setText(previous))


class DictationWorker(QThread):
    """Whisper transcription off the GUI thread -- no LLM call, just raw speech-to-text."""

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
            self.failed.emit(str(e))
            return
        finally:
            try:
                os.remove(self.wav_path)
            except OSError:
                pass

        if text.strip():
            self.transcribed.emit(text.strip())


class DictationController(QObject):
    """Hold a hotkey, speak, release -- transcript gets typed at the cursor via
    clipboard + simulated paste. No LLM involved, just raw speech-to-text."""

    def __init__(self, config, mascot=None, pill=None):
        super().__init__()
        self.config = config
        self.mascot = mascot
        self.pill = pill
        self.transcriber = WhisperTranscriber(config)
        self._worker = None

        self.push_to_talk = PushToTalk(config.get("dictation_hotkey"), config)
        if self.pill:
            self.push_to_talk.amplitude.connect(self.pill.update_amplitude)
        self.push_to_talk.started.connect(self._on_started)
        self.push_to_talk.finished.connect(self._on_recorded)
        self.push_to_talk.start()

    def _on_started(self):
        if self.mascot:
            self.mascot.reset_roaming()
            self.mascot.set_state("wondering_right")
        if self.pill:
            self.pill.start_listening()

    def _on_recorded(self, wav_path):
        if not wav_path:
            if self.mascot:
                self.mascot.set_state("idle")
            if self.pill:
                self.pill.return_to_idle()
                self.pill.show_response("No audio captured — check your mic in Settings.")
            return
        # Stay in "thinking" state while transcribing — pill shows thinking animation
        if self.pill:
            self.pill.start_thinking()
        self._worker = DictationWorker(self.transcriber, wav_path)
        self._worker.transcribed.connect(self._on_transcribed)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_transcribed(self, text):
        _win_paste(text)
        if self.mascot:
            self.mascot.set_state("idle")
        if self.pill:
            self.pill.return_to_idle()

    def _on_failed(self, message):
        if self.mascot:
            self.mascot.set_state("idle")
        if self.pill:
            self.pill.return_to_idle()
            self.pill.show_response(f"Dictation hiccup: {message}")

    def stop(self):
        self.push_to_talk.stop()
