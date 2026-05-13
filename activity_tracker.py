from pynput import mouse, keyboard
import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

class ActivityTracker(QObject):
    """
    Monitors mouse and keyboard input to detect user activity.
    """
    activity_detected = pyqtSignal(bool) # True if active, False if idle

    def __init__(self, check_interval_sec=5, idle_threshold_sec=60):
        super().__init__()
        self.check_interval_sec = check_interval_sec
        self.idle_threshold_sec = idle_threshold_sec
        
        self.last_activity_time = time.time()
        self.is_active = True
        self._last_signal_time = 0 # Throttling signal emissions
        
        # Initialize listeners
        self.mouse_listener = mouse.Listener(
            on_move=self._on_activity,
            on_click=self._on_activity,
            on_scroll=self._on_activity
        )
        self.kb_listener = keyboard.Listener(
            on_press=self._on_activity
        )
        
        # Start listeners
        self.mouse_listener.start()
        self.kb_listener.start()
        
        # Timer for idle transition
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self.check_idle_status)
        self.check_timer.start(self.check_interval_sec * 1000)

    def stop(self):
        """Cleanly stop the background threads."""
        try:
            self.mouse_listener.stop()
            self.kb_listener.stop()
            self.check_timer.stop()
        except Exception as e:
            pass

    def _on_activity(self, *args, **kwargs):
        """Callback for any input event. Signal emission is direct to ensure responsiveness."""
        now = time.time()
        self.last_activity_time = now
        
        if not self.is_active:
            self.is_active = True
            self.activity_detected.emit(True)
        
        # We still update the last signal time but we don't block the TRUE signal
        # to ensure the timer manager stays updated without huge overhead
        if now - self._last_signal_time > 1:
            self._last_signal_time = now
            self.activity_detected.emit(True)

    def check_idle_status(self):
        """Checks if the user has been idle for long enough to trigger idle state."""
        current_time = time.time()
        idle_duration = current_time - self.last_activity_time
        
        if idle_duration >= self.idle_threshold_sec:
            if self.is_active:
                self.is_active = False
                self.activity_detected.emit(False)
