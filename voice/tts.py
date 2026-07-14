import os
import re
import tempfile
import asyncio
import urllib.request
from abc import ABC, abstractmethod

DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # ZWJ
    "\U000025A0-\U000025FF"  # geometric shapes
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "]+",
    flags=re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


class Speaker(ABC):
    """Synthesizes text to a local audio file. Playback is the caller's job."""

    @abstractmethod
    def speak(self, text: str) -> str:
        """Returns path to a temp audio file (mp3). Raises on failure."""


class EdgeTTSSpeaker(Speaker):
    def __init__(self, config):
        self.config = config

    def speak(self, text: str) -> str:
        import edge_tts

        text = _strip_emojis(text)
        voice = self.config.get("tts_voice")
        rate = self.config.get("tts_rate")
        pitch = self.config.get("tts_pitch")
        volume = self.config.get("tts_volume")

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        async def synth():
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
            await communicate.save(path)

        try:
            asyncio.run(synth())
        except Exception:
            asyncio.run(synth())  # one retry for a transient endpoint hiccup, then let it raise
        return path


class ElevenLabsSpeaker(Speaker):
    """Falls back silently to EdgeTTSSpeaker if API key/quota is missing or the call fails."""

    def __init__(self, config):
        self.config = config
        self._fallback = EdgeTTSSpeaker(config)

    def speak(self, text: str) -> str:
        key = self.config.get("elevenlabs_api_key")
        if not key:
            return self._fallback.speak(text)

        text = _strip_emojis(text)
        voice_id = self.config.get("elevenlabs_voice_id") or DEFAULT_ELEVENLABS_VOICE_ID
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        import json
        body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    return self._fallback.speak(text)
                audio = resp.read()
        except Exception:
            return self._fallback.speak(text)

        fd, path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return path


def get_speaker(config) -> Speaker:
    if config.get("tts_backend") == "elevenlabs":
        return ElevenLabsSpeaker(config)
    return EdgeTTSSpeaker(config)
