import io
import wave
from collections import deque

import numpy as np
import sounddevice as sd
from groq import Groq
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from audio_devices import resolve_input_device, best_input_device, _is_junk
from hotkeys import HotkeyPoller

SAMPLE_RATE = 16000


SILENT_PEAK = 10  # int16 peak below this after the watchdog window = dead capture device
WATCHDOG_MS = 1500  # Bluetooth HFP mics often take >500ms to start delivering audio after open
NORMALIZE_TARGET = 26000  # boost quiet mics (weak headphone mics etc.) to this peak before Whisper
WARMUP_MS = 1000  # how long to hold the warmup stream open for BT handshake to settle


def warmup_mic(config=None):
    """Opens the configured (or best-guess) input device once at app startup and
    closes it shortly after, so a Bluetooth mic's HFP handshake is already done
    by the time the user's first real recording starts — instead of eating into
    that recording via the watchdog fallback."""
    device = resolve_input_device(config.get("mic_device")) if config else best_input_device()
    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device)
        stream.start()
    except Exception:
        return

    def _close():
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass

    QTimer.singleShot(WARMUP_MS, _close)


class Recorder(QObject):
    amplitude = pyqtSignal(float)

    _known_good = None  # class-level: device index that actually delivered audio this session

    def __init__(self):
        super().__init__()
        self._frames = []
        self._stream = None
        self._candidates = []
        self._levels = deque(maxlen=9)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._flush_levels)
        self._poll_timer.setInterval(60)
        # Bluetooth hands-free endpoints often open fine but deliver zero/near-zero
        # frames (profile not engaged). Watchdog hops to the next device when that happens.
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._check_signal)

    def start(self, device=None):
        self._frames = []
        self._levels.clear()
        self._poll_timer.start()
        self._candidates = self._fallback_candidates(device)
        self._open_next()
        self._watchdog.start(WATCHDOG_MS)

    def _fallback_candidates(self, device):
        auto = best_input_device()
        cands = [device, Recorder._known_good, auto]
        # Add all input devices as fallbacks — the watchdog will skip silent ones
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and not _is_junk(d["name"]):
                    cands.append(i)
        except Exception:
            pass
        seen, out = set(), []
        for c in cands:
            if c is not None and c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _open_next(self):
        """Open the next candidate device; skip ones that fail to open outright."""
        self._close_stream()
        while self._candidates:
            device = self._candidates.pop(0)
            try:
                self._frames = []
                dev_name = sd.query_devices(device)["name"] if device is not None else "(system default)"
                print(f"[miku] mic: opening device {device} — {dev_name}")
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=device,
                    callback=self._on_audio, blocksize=2048
                )
                self._stream.start()
                return
            except Exception:
                self._stream = None
        # every device failed to open; stop() will return "" (no frames)

    def _check_signal(self):
        if self._stream is None:
            return
        peak = 0
        if self._frames:
            peak = int(max(int(np.abs(f).max()) for f in self._frames))
        if peak < SILENT_PEAK and self._candidates:
            self._open_next()
            self._watchdog.start(WATCHDOG_MS)
        elif peak >= SILENT_PEAK:
            Recorder._known_good = self._stream.device  # remember what actually works

    def _close_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _flush_levels(self):
        while self._levels:
            self.amplitude.emit(self._levels.popleft())

    def _on_audio(self, indata, frames, time_info, status):
        self._frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        # int16 speech RMS runs ~300-4000; normalize so bars move with voice, not just noise
        self._levels.append(min(1.0, (rms / 32768.0) * 18.0))

    def stop(self) -> str | tuple:
        self._poll_timer.stop()
        self._watchdog.stop()
        self._flush_levels()
        self._close_stream()
        if not self._frames:
            print("[miku] mic: no frames captured")
            return ""
        audio = np.concatenate(self._frames, axis=0)
        peak = int(np.abs(audio).max())
        duration = len(audio) / SAMPLE_RATE
        print(f"[miku] mic: {len(audio)} samples, {duration:.1f}s, peak={peak}")
        # Weak mics (e.g. some headphone mics) pass the dead-stream check but are too
        # quiet for Whisper to transcribe reliably (it hallucinates "." on faint audio).
        # Boost gain to a healthy peak instead of sending it as-is.
        if 0 < peak < NORMALIZE_TARGET:
            audio = (audio.astype(np.float32) * (NORMALIZE_TARGET / peak)).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return ("audio.wav", buf.getvalue(), "audio/wav")


class WhisperTranscriber:
    def __init__(self, config):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            key = self.config.get("groq_api_key")
            if not key:
                raise RuntimeError("Groq API key not set.")
            self._client = Groq(api_key=key)
        return self._client

    def transcribe(self, audio) -> str:
        client = self._get_client()
        result = client.audio.transcriptions.create(
            file=audio,
            model="whisper-large-v3-turbo",
        )
        return result.text


class PushToTalk(QObject):
    """Hold a hotkey combo to record, release to stop. Uses RegisterHotKey for
    event-driven activation + lightweight polling for release detection.
    Builds WAV in memory (no disk I/O) and passes bytes directly to Groq."""

    started = pyqtSignal()
    finished = pyqtSignal(object)
    amplitude = pyqtSignal(float)

    def __init__(self, hotkey_str: str, config=None):
        super().__init__()
        self.config = config
        self._active = False
        self.recorder = Recorder()
        self.recorder.amplitude.connect(self.amplitude.emit)
        self._poller = HotkeyPoller(hotkey_str)
        self._poller.pressed.connect(self._on_press)
        self._poller.released.connect(self._on_release)

    def start(self):
        self._poller.start()

    def stop(self):
        self._poller.stop()  # emits released if currently held -> finishes cleanly
        if self._active:
            self._on_release()

    def _on_press(self):
        if self._active:
            return
        self._active = True
        device = resolve_input_device(self.config.get("mic_device")) if self.config else None
        self.recorder.start(device=device)
        self.started.emit()

    def _on_release(self):
        if not self._active:
            return
        self._active = False
        path = self.recorder.stop()
        self.finished.emit(path)
