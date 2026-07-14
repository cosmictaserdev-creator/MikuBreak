import json
import os

class ConfigManager:
    """Manages the application configuration in config.json."""
    
    DEFAULT_CONFIG = {
        "reminder_interval_min": 20,
        "snooze_duration_min": 10,
        "break_duration_min": 1,
        "is_paused": False,
        "run_at_startup": False,
        "dnd_enabled": False,
        "llm_provider": "groq",
        "groq_api_key": "",
        "groq_model": "llama-3.3-70b-versatile",
        "groq_vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "opencode_api_key": "",
        "opencode_model": "big-pickle",
        "chat_hotkey": "<ctrl>+<alt>+m",
        "voice_chat_hotkey": "<ctrl>+<alt>+v",
        "screen_guide_hotkey": "<ctrl>+<alt>+s",
        "dictation_hotkey": "<ctrl>+<alt>+f",
        "mic_device": "",
        "speaker_device": "",
        "screen_guide_blocklist": ["password", "keepass", "bitwarden", "1password", "bank", "wallet"],
        "tts_backend": "edge",
        "tts_voice": "en-US-JennyNeural",
        "tts_rate": "+0%",
        "tts_pitch": "+0Hz",
        "tts_volume": "+0%",
        "elevenlabs_api_key": "",
        "elevenlabs_voice_id": "",
        "muted": False,
        "screen_guide_enabled": True,
        "chatter_enabled": False,
        "chatter_frequency": "occasional",
        "daily_recap_enabled": True,
        "last_recap_date": "",
        "focus_blocklist": ["youtube", "netflix", "instagram", "tiktok", "twitter", "reddit", "prime video"],
        "shake_reversal_threshold": 4,
        "shake_grace_period_ms": 1200
    }
    
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        """Loads configuration from file or returns defaults."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return {**self.DEFAULT_CONFIG, **json.load(f)}
            except Exception as e:
                pass
        return self.DEFAULT_CONFIG.copy()

    def save_config(self):
        """Saves current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            pass

    def get(self, key):
        """Gets a configuration value."""
        return self.config.get(key, self.DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        """Sets a configuration value and saves."""
        self.config[key] = value
        self.save_config()
