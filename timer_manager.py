from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from config import ConfigManager

class TimerManager(QObject):
    """
    Tracks active time and triggers the reminder sequence.
    """
    reminder_triggered = pyqtSignal()
    second_elapsed = pyqtSignal(int) # Current active seconds

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.active_seconds = 0
        self.is_running = True
        
        # Main timer (runs every second)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def tick(self):
        """Called every second to increment the active counter."""
        if not self.is_running or self.config.get("is_paused"):
            return
            
        self.active_seconds += 1
        # Always fetch fresh value from config
        interval_min = self.config.get("reminder_interval_min")
        limit_seconds = int(interval_min * 60)
        
        # Check if we reached the limit
        remaining = max(0, limit_seconds - self.active_seconds)
        self.second_elapsed.emit(remaining)
        
        if self.active_seconds >= limit_seconds:
            self.reminder_triggered.emit()
            self.stop() # Stop until reset

    def set_active(self, active: bool):
        """Enables/disables tracking based on user activity."""
        self.is_running = active
        if active and not self.config.get("is_paused"):
            if not self.timer.isActive():
                self.timer.start(1000)
        else:
            self.timer.stop()

    def reset(self, minutes_offset=0):
        """Resets the timer, optionally with an offset (snooze)."""
        if minutes_offset > 0:
            limit_seconds = self.config.get("reminder_interval_min") * 60
            self.active_seconds = max(0, limit_seconds - (minutes_offset * 60))
        else:
            self.active_seconds = 0
            
        self.is_running = True
        if not self.config.get("is_paused"):
            self.timer.start(1000)

    def stop(self):
        """Stops the timer tracking."""
        self.is_running = False
        self.timer.stop()
