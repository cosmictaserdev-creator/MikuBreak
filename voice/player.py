import os

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from audio_devices import apply_output_device


class SpeechPlayer(QObject):
    """Plays one synthesized speech clip at a time and deletes its temp file
    when done. mediaStatusChanged is connected exactly once, here, instead of
    per-call at each caller — the old per-call connect()s never got
    disconnected when playback was interrupted, so they piled up over a
    session and each real EndOfMedia fired every stale one."""

    finished = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        apply_output_device(self.audio_output, config)
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_status)
        self._pending_path = None

    def play(self, audio_path):
        self._cleanup_pending()
        self._pending_path = audio_path
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.player.play()

    def is_playing(self):
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def stop(self):
        if self.is_playing():
            self.player.stop()
        self._cleanup_pending()

    def set_output_device(self, config):
        apply_output_device(self.audio_output, config)

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.stop()
            self._cleanup_pending()
            self.finished.emit()

    def _cleanup_pending(self):
        if self._pending_path:
            try:
                os.remove(self._pending_path)
            except OSError:
                pass
            self._pending_path = None
