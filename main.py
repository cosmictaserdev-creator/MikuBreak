import sys
import os
import random
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QFontDatabase
from PyQt6.QtCore import QTimer, QSharedMemory
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from mascot_window import MascotWindow
from sprite_loader import SpriteLoader
from config import ConfigManager
from activity_tracker import ActivityTracker
from timer_manager import TimerManager
from reminder_window import ReminderWindow
from settings_window import SettingsWindow
from chat_controller import ChatController
from memory.store import MemoryStore
from memory_scheduler import MemoryScheduler
from screen_guide import ScreenGuideController
from pill import MikuPill
from idle_chatter import IdleChatter
from dictation import DictationController
from stt.groq_whisper import warmup_mic

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class ScreenPalApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("mikuBreak")
        self.app.setQuitOnLastWindowClosed(False)
        
        # Single Instance Enforcement. QLocalServer.listen() alone isn't a real mutex on
        # Windows (named pipes allow multiple listeners on the same name), so the actual
        # lock is a QSharedMemory segment; QLocalServer is only used to message the
        # survivor. If the segment already exists, another instance owns it.
        self.instance_name = "mikuBreak_unique_id"
        self.singleton_lock = QSharedMemory("mikuBreak_singleton_lock")
        if not self.singleton_lock.create(1):
            self.notify_existing_instance()
            if not self.singleton_lock.create(1):
                sys.exit(0)  # old instance didn't release the lock in time

        self.server = QLocalServer(self.app)
        self.server.newConnection.connect(self.handle_new_instance)
        QLocalServer.removeServer(self.instance_name)  # clear a stale pipe registration from a crashed run
        self.server.listen(self.instance_name)

        # Register Custom Fonts
        self.load_fonts()
        
        # Initialize Managers (Order is important!)
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        self.config = ConfigManager(config_path=os.path.join(base_path, "config.json"))
        self.loader = SpriteLoader()
        self.store = MemoryStore(db_path=os.path.join(base_path, "miku_memory.db"))

        # UI Components
        self.mascot = MascotWindow(self.loader, self.config)
        self.mascot.shake_detected.connect(self.handle_shake_detected)
        self.mascot.shake_resolved.connect(self.handle_shake_resolved)
        # file_dropped connected after chat_controller exists (below)
        self.pill = MikuPill(self.mascot)
        self.chat_controller = ChatController(self.config, self.mascot, self.store, self.pill)
        self.mascot.file_dropped.connect(self.chat_controller.handle_file_drop)
        self.screen_guide = ScreenGuideController(self.config, self.mascot, self.store, self.pill, chat_controller=self.chat_controller)
        self.memory_scheduler = MemoryScheduler(self.store, self.chat_controller)
        self.memory_scheduler.start()
        self.idle_chatter = IdleChatter(self.config, self.chat_controller)
        self.idle_chatter.start()
        self.dictation = DictationController(self.config, mascot=self.mascot, pill=self.pill)
        self._interrupted_nudge = None

        warmup_mic(self.config)

        # Set initial timer display after a small delay to ensure UI is ready
        QTimer.singleShot(200, self.set_initial_timer)

        # First launch of the day: short good-morning recap (reminders, habits)
        QTimer.singleShot(8000, self.maybe_daily_recap)
        
        self.reminder = None
        self.settings_window = None
        
        # Logic Components
        self.tracker = ActivityTracker()
        self.timer_manager = TimerManager(self.config)
        self.is_on_break = False
        
        # Connect Signals
        self.tracker.activity_detected.connect(self.handle_activity_change)
        self.timer_manager.reminder_triggered.connect(self.start_reminder_sequence)
        self.timer_manager.second_elapsed.connect(self.mascot.update_timer_display)
        self.timer_manager.second_elapsed.connect(self.update_pill_countdown)
        
        self.setup_tray()

    def notify_existing_instance(self):
        """We lost the race for the server name -- tell whoever holds it to quit."""
        socket = QLocalSocket()
        socket.connectToServer(self.instance_name)
        if socket.waitForConnected(500):
            socket.write(b"QUIT")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            # Wait for the old one to actually release the server name
            import time
            time.sleep(1)

    def handle_new_instance(self):
        """Called in the OLD instance when a new one tries to start."""
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(1000):
            msg = socket.readAll().data().decode()
            if msg == "QUIT":
                self.quit_app()

    def set_initial_timer(self):
        """Sets the starting countdown value on the mascot."""
        initial_seconds = int(self.config.get("reminder_interval_min") * 60)
        self.mascot.update_timer_display(initial_seconds)
        self.update_pill_countdown(initial_seconds)

    def update_pill_countdown(self, remaining_seconds):
        self.pill.show_countdown(remaining_seconds)

    def load_fonts(self):
        font_dir = resource_path(os.path.join("font", "DM_Serif_Display"))
        regular_path = os.path.join(font_dir, "DMSerifDisplay-Regular.ttf")
        italic_path = os.path.join(font_dir, "DMSerifDisplay-Italic.ttf")
        
        if os.path.exists(regular_path):
            QFontDatabase.addApplicationFont(regular_path)
        if os.path.exists(italic_path):
            QFontDatabase.addApplicationFont(italic_path)

    def handle_activity_change(self, is_active):
        """Pass activity state to timer manager and handle 'Angry Miku' during breaks."""
        # ONLY update timer manager if NOT on a break
        if not self.is_on_break:
            self.timer_manager.set_active(is_active)
        
        # If user is supposed to be on break but is using the PC
        if self.is_on_break and self.reminder:
            # If the user is dragging the mascot, don't trigger "Angry Miku" behavior changes
            if self.mascot.dragging:
                if hasattr(self, "angry_trigger_timer"):
                    self.angry_trigger_timer.stop()
                return

            if is_active:
                # If we are already in angry/smart mode, don't restart the trigger timer
                if getattr(self, "is_currently_angry", False):
                    return

                # Start a timer to trigger "Angry Miku" after 2 seconds of continuous activity
                if not hasattr(self, "angry_trigger_timer"):
                    self.angry_trigger_timer = QTimer()
                    self.angry_trigger_timer.setSingleShot(True)
                    self.angry_trigger_timer.timeout.connect(self.trigger_angry_miku)
                
                if not self.angry_trigger_timer.isActive():
                    self.angry_trigger_timer.start(2000) # 2 seconds threshold
            else:
                # User stopped, cancel trigger timer
                if hasattr(self, "angry_trigger_timer"):
                    self.angry_trigger_timer.stop()
                
                # If they weren't already angry, ensure they stay in a relaxed state
                if not getattr(self, "is_currently_angry", False):
                    choice = random.choice(["sitting", "sleeping"])
                    self.mascot.set_state(choice)
                    self.reminder.set_angry_mode(False)

    def trigger_angry_miku(self):
        """Actually switches mascot and window to angry state."""
        if self.is_on_break and self.reminder and self.tracker.is_active:
            self.is_currently_angry = True
            self.mascot.set_state("pulling")
            self.reminder.set_angry_mode(True)
            
            # Start a timer to revoke angry mode after 10 seconds as requested
            QTimer.singleShot(10000, self.revoke_angry_mode)

    def revoke_angry_mode(self):
        """Returns to relaxed state during break after 10 seconds of angry mode."""
        self.is_currently_angry = False
        if self.is_on_break and self.reminder:
            self.reminder.set_angry_mode(False)
            choice = random.choice(["sitting", "sleeping"])
            self.mascot.set_state(choice)

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        icon_path = resource_path(os.path.join("assests", "appIcon.png"))
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            # Fallback to secondary icon
            secondary_path = resource_path(os.path.join("assests", "img", "icon.png"))
            if os.path.exists(secondary_path):
                self.tray_icon.setIcon(QIcon(secondary_path))
            else:
                self.tray_icon.setIcon(self.app.style().standardIcon(self.app.style().StandardPixmap.SP_ComputerIcon))
            
        tray_menu = QMenu()
        
        # Menu Actions
        settings_action = tray_menu.addAction("Settings")
        settings_action.triggered.connect(self.show_settings)
        
        self.pause_action = tray_menu.addAction("Pause")
        self.pause_action.setCheckable(True)
        self.pause_action.setChecked(self.config.get("is_paused"))
        self.pause_action.triggered.connect(self.toggle_pause)

        self.mute_action = tray_menu.addAction("Mute Voice")
        self.mute_action.setCheckable(True)
        self.mute_action.setChecked(self.config.get("muted"))
        self.mute_action.triggered.connect(self.toggle_mute)

        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def quit_app(self):
        """Clean shutdown of threads and app."""
        self.tracker.stop()
        self.chat_controller.stop()
        self.screen_guide.stop()
        self.memory_scheduler.stop()
        self.idle_chatter.stop()
        self.dictation.stop()
        self.app.quit()

    def show_settings(self):
        if not self.settings_window:
            self.settings_window = SettingsWindow(self.config, self.store)
            self.settings_window.settings_changed.connect(self.handle_settings_change)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def handle_settings_change(self):
        self.timer_manager.reset() # Reset to start fresh with new interval
        # Force an immediate UI update with the new setting
        self.set_initial_timer()

    def maybe_daily_recap(self):
        """Once per calendar day, on first launch: Miku greets with today's reminders/habits."""
        if not self.config.get("daily_recap_enabled") or not self.config.get("groq_api_key"):
            return
        import datetime
        today = datetime.date.today().isoformat()
        if self.config.get("last_recap_date") == today:
            return
        if self.mascot.dragging or not self.pill.is_idle():
            QTimer.singleShot(60000, self.maybe_daily_recap)  # busy — try again in a minute
            return
        self.config.set("last_recap_date", today)
        self.chat_controller.handle_prompt(
            "Greet the user for the start of their day. If your context lists reminders or "
            "tracked habits for today, mention them briefly; otherwise just a warm one-line "
            "hello. Two or three short sentences max."
        )

    def toggle_pause(self):
        is_paused = self.pause_action.isChecked()
        self.config.set("is_paused", is_paused)

    def toggle_mute(self):
        muted = self.mute_action.isChecked()
        self.config.set("muted", muted)

    def handle_shake_detected(self):
        """Shake-to-pause: interrupt whatever she's doing, play a startled beat."""
        interrupted = self.chat_controller.interrupt()
        if interrupted:
            self._interrupted_nudge = interrupted
        self.screen_guide.speech.stop()
        # ponytail: no dedicated startled/dizzy sprite frames exist yet — reuse the
        # single "turn" frame as a quick flinch. Swap in real frames if art shows up.
        self.mascot.set_state("turn")

    def handle_shake_resolved(self):
        """Drag released + grace period elapsed: resume normal behavior, or a nudge she was mid-delivery on."""
        if self._interrupted_nudge:
            text, self._interrupted_nudge = self._interrupted_nudge, None
            self.chat_controller.deliver_nudge(text)
        else:
            self.mascot.set_state("idle")

    def start_reminder_sequence(self):
        """Phase 1: Mascot walks/runs to center while playing dialog animation."""
        
        # DND: skip reminder entirely
        if self.config.get("dnd_enabled"):
            return

        # SAFETY: If a reminder is already visible or we are on break, ignore
        if self.reminder and self.reminder.isVisible():
            return
            
        if self.is_on_break:
            return

        # Cooldown: Don't trigger another reminder if one just finished (within 30s)
        import time
        if hasattr(self, "last_break_end_time") and (time.time() - self.last_break_end_time < 30):
            return

        # If user is currently dragging Miku, wait for release before starting sequence
        if self.mascot.dragging:
            QTimer.singleShot(1000, self.start_reminder_sequence)
            return

        # Reset roaming/movement before starting reminder sequence
        self.mascot.reset_roaming()
        
        screen = self.mascot.screen().availableGeometry()
        target_x = (screen.width() - self.mascot.width()) // 2
        self.mascot.anchor_before_reminder = self.mascot.x() # Remember where she came from
        
        # Walk to center with custom 'dialog' state
        self.mascot.walk_to(target_x, self.show_reminder, speed=6, state="dialog")

    def show_reminder(self):
        """Phase 2: Show the centered popup and make mascot hold."""
        # Final safety check before showing
        if self.reminder and self.reminder.isVisible():
            return
            
        self.mascot.set_state("dialog_holding") # Persistent holding pose
        # Pass values from config to the window
        interval = self.config.get("reminder_interval_min")
        snooze = self.config.get("snooze_duration_min")
        break_dur = self.config.get("break_duration_min")
        self.reminder = ReminderWindow(self.loader, interval_min=interval, snooze_min=snooze, break_min=break_dur)
        self.reminder.action_taken.connect(self.handle_reminder_action)
        self.reminder.break_finished.connect(self.handle_break_finished)
        self.reminder.timer_updated.connect(self.mascot.update_timer_display)
        self.reminder.show()

    def handle_reminder_action(self, action):
        """Phase 3: Mascot reacts based on user choice."""
        
        if action == "snooze":
            self.is_on_break = False
            snooze_min = self.config.get("snooze_duration_min")
            self.timer_manager.reset(snooze_min)
            # Ensure prompt window is cleared after feedback delay
            QTimer.singleShot(3000, self.walk_back)
            
        elif action == "break":
            self.is_on_break = True
            self.is_currently_angry = False
            self.timer_manager.stop() # Stop tracking work time during break
            
            # Immediately check if the user is active to show "Angry Miku" if needed
            if self.tracker.is_active:
                self.handle_activity_change(True)
            else:
                # Mascot sits or sleeps during the break
                choice = random.choice(["sitting", "sleeping"])
                self.mascot.set_state(choice)
            # The window will signal break_finished when the countdown ends
            
        else: # dismiss
            self.is_on_break = False
            self.timer_manager.reset()
            # If user dismissed, they are definitely active, so keep timer going
            self.timer_manager.set_active(True)
            QTimer.singleShot(3000, self.walk_back)

    def handle_break_finished(self):
        """Phase 4: Break is over, mascot returns home."""
        import time
        self.is_on_break = False
        self.is_currently_angry = False
        self.last_break_end_time = time.time()
        self.timer_manager.reset() # Start tracking again after break
        # We wait a bit so the user can see the "Good boy" message
        QTimer.singleShot(5000, self.walk_back)


    def walk_back(self):
        # Prefer returning home to the actual corner (anchor_x)
        # instead of wherever she was roaming (anchor_before_reminder)
        target_x = getattr(self.mascot, "anchor_x", 0)
        
        if target_x == 0:
             screen = self.mascot.screen().availableGeometry()
             target_x = screen.width() - self.mascot.width() - 50
             
        self.mascot.walk_to(target_x, self.finish_sequence, speed=8, state="run")

    def finish_sequence(self):
        self.mascot.set_state("idle")

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    app = ScreenPalApp()
    app.run()
