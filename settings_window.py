from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QFrame, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QPalette, QBrush
from config import ConfigManager
import os
import sys

class SettingsWindow(QWidget):
    """
    Aesthetic UI for changing reminder intervals and snooze durations with sliders and bg.
    """
    settings_changed = pyqtSignal()

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        
        self.setWindowTitle("mikuBreak Control Room")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(500, 680) # Increased height for startup toggle
        
        # Cyber-Cute Miku Theme with Background Support
        self.setup_background()
        
        self.setStyleSheet("""
            QWidget {
                color: #959bb5;
                font-family: 'DM Serif Display', serif;
            }
            QFrame#mainOverlay {
                background-color: rgba(10, 17, 35, 220);
                border-radius: 20px;
            }
            QLabel#headerTitle {
                color: #8387c4;
                font-size: 28px;
                font-weight: 900;
                background: transparent;
            }
            QLabel#sliderVal {
                color: #898cab;
                font-size: 18px;
                font-weight: 800;
            }
            QLabel {
                font-size: 15px;
                font-weight: 600;
                color: #8387c4;
                background: transparent;
            }
            QCheckBox {
                color: #8387c4;
                font-size: 15px;
                font-weight: 600;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #8387c4;
                background: #1a1e2e;
            }
            QCheckBox::indicator:checked {
                background: #8387c4;
            }
            QSlider::handle:horizontal {
                background: #8387c4;
                border: 2px solid #FFFFFF;
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #8387c4;
                height: 8px;
                background: #1a1e2e;
                margin: 2px 0;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #8387c4;
                color: #0a1123;
                border: none;
                padding: 12px;
                border-radius: 15px;
                font-weight: 900;
                font-size: 14px;
                text-transform: uppercase;
            }
            QPushButton:hover {
                background-color: #898cab;
            }
            QPushButton#cancelBtn {
                background-color: #3a3e6d;
                color: #959bb5;
            }
        """)
        
        self.init_ui()

    def setup_background(self):
        bg_path = os.path.join("assests", "bg.jpg")
        if os.path.exists(bg_path):
            palette = QPalette()
            pixmap = QPixmap(bg_path).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            palette.setBrush(QPalette.ColorRole.Window, QBrush(pixmap))
            self.setPalette(palette)
            self.setAutoFillBackground(True)

    def init_ui(self):
        # Use an overlay frame to keep text readable over BG
        self.overlay = QFrame(self)
        self.overlay.setObjectName("mainOverlay")
        self.overlay.setGeometry(20, 20, 460, 640)
        
        layout = QVBoxLayout(self.overlay)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("✧ mikuBreak Control Room ✧")
        header.setObjectName("headerTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #8387c4; min-height: 2px;")
        layout.addWidget(line)

        # Reminder Interval Slider
        layout.addWidget(QLabel("How often should I bug you? (Minutes)"))
        self.interval_label = QLabel()
        self.interval_label.setObjectName("sliderVal")
        self.interval_slider = self.create_slider(5, 120, self.config.get("reminder_interval_min"))
        self.interval_slider.valueChanged.connect(lambda v: self.interval_label.setText(f"{v}m"))
        self.interval_label.setText(f"{self.interval_slider.value()}m")
        
        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(self.interval_slider)
        h_layout1.addWidget(self.interval_label)
        layout.addLayout(h_layout1)
        
        # Snooze Duration Slider
        layout.addWidget(QLabel("Extra 'just five more minutes' time?"))
        self.snooze_label = QLabel()
        self.snooze_label.setObjectName("sliderVal")
        self.snooze_slider = self.create_slider(1, 30, self.config.get("snooze_duration_min"))
        self.snooze_slider.valueChanged.connect(lambda v: self.snooze_label.setText(f"{v}m"))
        self.snooze_label.setText(f"{self.snooze_slider.value()}m")
        
        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(self.snooze_slider)
        h_layout2.addWidget(self.snooze_label)
        layout.addLayout(h_layout2)
        
        # Break Duration Slider
        layout.addWidget(QLabel("How long is our cozy break?"))
        self.break_label = QLabel()
        self.break_label.setObjectName("sliderVal")
        self.break_slider = self.create_slider(1, 60, self.config.get("break_duration_min"))
        self.break_slider.valueChanged.connect(lambda v: self.break_label.setText(f"{v}m"))
        self.break_label.setText(f"{self.break_slider.value()}m")
        
        h_layout3 = QHBoxLayout()
        h_layout3.addWidget(self.break_slider)
        h_layout3.addWidget(self.break_label)
        layout.addLayout(h_layout3)

        # Run at Startup
        self.startup_check = QCheckBox("Run mikuBreak on system startup")
        self.startup_check.setChecked(self.config.get("run_at_startup"))
        layout.addWidget(self.startup_check)
        
        # Interaction Tip
        tip_label = QLabel("✨ Tip: Press Control + Click to interact or drag Miku!")
        tip_label.setStyleSheet("color: #898cab; font-style: italic; font-size: 13px; margin-top: 10px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.save_btn = QPushButton("Save & Keep Working ✨")
        self.save_btn.clicked.connect(self.save_settings)
        
        self.cancel_btn = QPushButton("Nevermind~")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.close)
        
        btn_layout.addWidget(self.save_btn, 2)
        btn_layout.addWidget(self.cancel_btn, 1)
        layout.addLayout(btn_layout)

    def create_slider(self, min_v, max_v, curr_v):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(int(curr_v))
        return slider

    def save_settings(self):
        # Update config
        self.config.set("reminder_interval_min", self.interval_slider.value())
        self.config.set("snooze_duration_min", self.snooze_slider.value())
        self.config.set("break_duration_min", self.break_slider.value())
        
        startup_enabled = self.startup_check.isChecked()
        self.config.set("run_at_startup", startup_enabled)
        self.handle_startup_registry(startup_enabled)
        
        # Show Confirmation
        self.save_btn.setText("SAVED SUCCESSFULLY! ✨")
        self.save_btn.setStyleSheet("""
            background-color: #898cab;
            color: #0a1123;
            border: 2px solid #FFFFFF;
            padding: 12px;
            border-radius: 15px;
            font-weight: 900;
        """)
        
        # Emit signal for other components to react
        self.settings_changed.emit()
        
        # Delay closing so the user can see the "Saved" state
        QTimer.singleShot(1000, self.close)

    def handle_startup_registry(self, enable):
        """Manages the Windows registry key for running at startup."""
        if sys.platform != "win32":
            return
            
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "mikuBreak"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                # Add registry entry
                app_path = os.path.abspath(sys.argv[0])
                # If running as script, use python.exe path
                if not app_path.endswith(".exe"):
                    app_path = f'"{sys.executable}" "{app_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
            else:
                # Remove registry entry
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            pass

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    cfg = ConfigManager()
    win = SettingsWindow(cfg)
    win.show()
    sys.exit(app.exec())
