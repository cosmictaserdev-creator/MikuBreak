from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QFont, QPalette, QBrush
from sprite_loader import SpriteLoader
import os

class ReminderWindow(QWidget):
    """
    The centered popup window that reminds the user to take a break.
    """
    action_taken = pyqtSignal(str) # "break", "snooze", "dismiss"
    break_finished = pyqtSignal()
    timer_updated = pyqtSignal(int)

    def __init__(self, sprite_loader: SpriteLoader, interval_min: int = 20, snooze_min: int = 5, break_min: int = 1):
        super().__init__()
        self.loader = sprite_loader
        self.interval_min = interval_min
        self.snooze_min = snooze_min
        self.break_min = break_min
        self.break_timer = QTimer(self)
        self.break_timer.timeout.connect(self.update_break_timer)
        self.remaining_seconds = 0
        
        # Auto-break if no interaction
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.on_auto_timeout)
        self.auto_timer.start(int(self.break_min * 60 * 1000))
        
        # Window Setup
        self.setWindowTitle("mikuBreak")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # UI Layout
        self.init_ui()
        self.center_on_screen()

    def init_ui(self):
        self.setFixedSize(600, 500) # Ensure enough space for BG
        
        # Main Card (Cyber-Cute Theme)
        self.card = QFrame(self)
        self.card.setObjectName("mainCard")
        self.card.setGeometry(0, 0, 600, 500)
        
        # Background Setup
        # Use absolute paths for PyInstaller compatibility
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bg_path = os.path.join(script_dir, "assests", "bg.jpg")
        bg_style = ""
        if os.path.exists(bg_path):
            # Normalize path for CSS
            safe_bg_path = bg_path.replace("\\", "/")
            # Use background-image + cover-like styling for better radius support
            bg_style = f"""
                background-image: url({safe_bg_path});
                background-position: center;
                background-repeat: no-repeat;
            """

        self.card.setStyleSheet(f"""
            QFrame#mainCard {{
                {bg_style}
                border-radius: 30px;
                border: 3px solid #8387c4;
            }}
        """)
        
        # Inner overlay to keep text readable
        self.overlay = QFrame(self.card)
        self.overlay.setGeometry(0, 0, 600, 500)
        self.overlay.setStyleSheet("""
            background-color: rgba(10, 17, 35, 180);
            border-radius: 27px; /* Slightly smaller to fit inside 3px border */
        """)
        
        layout = QVBoxLayout(self.overlay)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(15)
        
        # Mascot Icon
        self.mascot_label = QLabel()
        self.set_mascot_image("initial")
        self.mascot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mascot_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.mascot_label)
        
        # Message (Cyber-Cute Style)
        self.message = QLabel(f"Hey! You've been active for {self.interval_min} minutes.\nTime for a cozy break! ✧")
        self.message.setStyleSheet("""
            color: #FFFFFF; 
            font-size: 26px; 
            font-weight: 900; 
            line-height: 1.4;
            font-family: 'DM Serif Display', serif;
            background: transparent;
        """)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message)
        
        # Timer Label
        self.timer_label = QLabel("")
        self.timer_label.setStyleSheet("""
            color: #8387c4; 
            font-size: 48px; 
            font-weight: 900; 
            font-family: 'DM Serif Display', serif;
            background-color: rgba(26, 30, 46, 200);
            border-radius: 15px;
            padding: 10px;
        """)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.hide()
        layout.addWidget(self.timer_label)

        # Buttons
        self.btn_container = QWidget()
        self.btn_container.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(self.btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(15)
        
        self.btn_break = self.create_button("☕ Cozy Break", "#8387c4", "break")
        self.btn_snooze = self.create_button(f"⏰ +{self.snooze_min} Min", "#898cab", "snooze")
        self.btn_dismiss = self.create_button("✖ Later~", "#3a3e6d", "dismiss")
        
        btn_layout.addWidget(self.btn_break)
        btn_layout.addWidget(self.btn_snooze)
        btn_layout.addWidget(self.btn_dismiss)
        
        layout.addWidget(self.btn_container)
        
        # Main Window Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.card)
        self.setLayout(main_layout)

    def set_mascot_image(self, state):
        mapping = {
            "initial": "initial prompt.jpg",
            "relax": "relexing.jpg",
            "smart": "try to be smart.jpg",
            "happy": "happy miku.jpg",
            "snooze": "snooze.jpg",
            "angry": "angry miku.jpg"
        }
        filename = mapping.get(state, "initial prompt.jpg")
        path = os.path.join("assests", "prompt", filename)
        if os.path.exists(path):
            pixmap = QPixmap(path)
            self.mascot_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def create_button(self, text, color, action):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: #0a1123;
                border: none;
                padding: 15px 20px;
                border-radius: 18px;
                font-size: 15px;
                font-weight: 900;
                font-family: 'DM Serif Display', serif;
            }}
            QPushButton:hover {{
                background-color: #FFFFFF;
                color: {color};
            }}
        """)
        btn.clicked.connect(lambda: self.on_click(action))
        return btn

    def on_click(self, action):
        self.auto_timer.stop() # User interacted, stop auto-break
        if action == "break":
            self.start_break_countdown(self.break_min * 60)
            self.set_mascot_image("relax")
            self.action_taken.emit(action)
        elif action == "snooze":
            self.set_mascot_image("snooze")
            self.show_feedback_screen(f"Got it! Reminding you in {self.snooze_min} minutes. \nSee you soon! ✨", "#8387c4")
            self.action_taken.emit(action)
            QTimer.singleShot(2000, self.close) 
        elif action == "dismiss":
            self.set_mascot_image("angry")
            self.show_feedback_screen("You are a naughty person! \nIgnoring Miku... 💢", "#F7768E")
            self.action_taken.emit(action)
            QTimer.singleShot(2000, self.close) 

    def show_feedback_screen(self, text, color):
        self.btn_container.hide()
        self.timer_label.hide()
        self.message.setText(text)
        self.message.setStyleSheet(f"""
            color: {color}; 
            font-size: 24px; 
            font-weight: 900; 
            line-height: 1.4;
            background: transparent; 
            font-family: 'DM Serif Display', serif;
        """)

    def start_break_countdown(self, seconds):
        self.btn_container.hide()
        self.remaining_seconds = seconds
        self.update_timer_label()
        self.timer_label.show()
        self.message.setText("Miku is watching over your PC! \nGo relax and stretch! 🌸")
        self.message.setStyleSheet("color: #898cab; font-size: 22px; font-weight: 900; background: transparent; font-family: 'DM Serif Display', serif;")
        self.break_timer.start(1000)

    def update_break_timer(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.break_timer.stop()
            self.timer_label.setText("00:00")
            self.set_mascot_image("happy")
            self.message.setText("You are such a good boy! \nYou can use your PC now. ✨")
            self.message.setStyleSheet("color: #8387c4; font-size: 24px; font-weight: 900; background: transparent; font-family: 'DM Serif Display', serif;")
            self.break_finished.emit()
            QTimer.singleShot(2000, self.close) # Reduced to 2s
        else:
            self.update_timer_label()

    def update_timer_label(self):
        mins = int(self.remaining_seconds // 60)
        secs = int(self.remaining_seconds % 60)
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")
        self.timer_updated.emit(int(self.remaining_seconds))

    def set_angry_mode(self, is_angry):
        """Changes the UI to show Miku is angry because the user is active during a break."""
        if is_angry:
            self.set_mascot_image("smart")
            self.overlay.setStyleSheet("""
                background-color: rgba(40, 20, 20, 220);
                border-radius: 30px;
                border: 4px solid #F7768E;
            """)
            self.message.setText("HEY! Go relax or Miku will be angry! \nStop using the PC! 💢")
            self.message.setStyleSheet("color: #F7768E; font-size: 22px; font-weight: 900; background: transparent; font-family: 'DM Serif Display', serif;")
        else:
            self.set_mascot_image("relax")
            self.overlay.setStyleSheet("""
                background-color: rgba(10, 17, 35, 180);
                border-radius: 30px;
            """)
            self.message.setText("Miku is watching over your PC! \nGo relax and stretch! 🌸")
            self.message.setStyleSheet("color: #898cab; font-size: 22px; font-weight: 900; background: transparent; font-family: 'DM Serif Display', serif;")


    def on_auto_timeout(self):
        """Automatically complete a break if user didn't touch the prompt."""
        self.set_mascot_image("happy")
        self.btn_container.hide()
        self.message.setText("You are such a good boy! \nYou can use your PC now. ✨")
        self.message.setStyleSheet("color: #8387c4; font-size: 24px; font-weight: 900; background: transparent; font-family: 'DM Serif Display', serif;")
        self.break_finished.emit()
        QTimer.singleShot(2000, self.close)

    def center_on_screen(self):
        screen = self.screen().availableGeometry()
        self.adjustSize()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    loader = SpriteLoader()
    window = ReminderWindow(loader)
    window.show()
    sys.exit(app.exec())
