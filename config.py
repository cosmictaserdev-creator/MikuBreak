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
        "dnd_enabled": False
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
