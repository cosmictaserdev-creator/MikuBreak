import os
import sys
import time
import random
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QFrame
from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QTransform, QGuiApplication
from behavior_scheduler import BehaviorScheduler

class MascotWindow(QWidget):
    """
    Refined mascot window with complex physics, distance-based drop animations,
    intelligent corner returning, and roaming idle behavior.
    """

    shake_detected = pyqtSignal()  # fast direction-reversal while dragging
    shake_resolved = pyqtSignal()  # drag released + grace period elapsed
    moved = pyqtSignal()  # fires every time the window's position actually changes
    file_dropped = pyqtSignal(str)  # user dropped a file from Explorer onto the mascot

    def __init__(self, sprite_loader=None, config=None):
        super().__init__()
        self.config = config
        self.setAcceptDrops(True)
        self.MASCOT_SIZE = 128
        self.TIMER_HEIGHT = 30
        self.BUBBLE_W = 76
        self.BUBBLE_H = 24
        self.setFixedSize(self.MASCOT_SIZE, self.MASCOT_SIZE + self.TIMER_HEIGHT)
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("QWidget { background: transparent; border: none; outline: none; }")

        # Timer Label above Mascot — rounded bubble
        self.timer_label = QLabel(self)
        self.timer_label.setGeometry(
            (self.MASCOT_SIZE - self.BUBBLE_W) // 2,
            3,
            self.BUBBLE_W,
            self.BUBBLE_H
        )
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-family: 'DM Serif Display', serif;
                font-size: 16px;
                font-weight: bold;
                background: rgba(0, 0, 0, 200);
                border-radius: 10px;
                padding: 2px 6px;
            }
        """)
        self.timer_label.setText("--:--")
        self.timer_label.hide()  # superseded by the floating MikuPill, which anchors to this same spot

        self.label = QLabel(self)
        self.label.setGeometry(0, self.TIMER_HEIGHT, self.MASCOT_SIZE, self.MASCOT_SIZE)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("QLabel { background: transparent; border: none; }")
        self.label.setFrameShape(QFrame.Shape.NoFrame)
        self.label.setFrameShadow(QFrame.Shadow.Plain)
    

        script_dir = os.path.dirname(os.path.abspath(__file__))
        assets_path = os.path.join(script_dir, "assests", "img")
        
        # Initialize Scheduler with callbacks
        self.scheduler = BehaviorScheduler(
            assets_path, 
            set_frame_callback=self.set_frame,
            behavior_changed_callback=self.on_behavior_changed
        )
        self.scheduler.on_wake_up_callback = self.start_wake_up_sequence
        
        # Physics & Interaction State
        self.dragging = False
        self.is_falling = False
        self.drag_start_pos = QPoint()
        self.last_mouse_pos = QPoint()
        self.current_direction = "left"
        self.is_clickable = False
        self._is_roaming = False
        self.behavior_y_offset = 0
        self.drop_frames_cycled = 0

        # Shake-to-pause tracking
        self._shake_reversals = []
        self._last_shake_sign = None
        self._shake_active = False

        # Anchor point for roaming returning
        self.anchor_x = 0

        # Timers
        self.drag_still_timer = QTimer()
        self.drag_still_timer.timeout.connect(self._on_drag_still)
        
        self.fall_timer = QTimer()
        self.fall_timer.timeout.connect(self._fall_step)
        
        self.key_check_timer = QTimer(self)
        self.key_check_timer.timeout.connect(self.check_modifier_key)
        self.key_check_timer.start(100)

        # Floating Window Host Tracking
        self.host_hwnd = None
        self.host_offset_x = 0
        self.host_offset_y = 0
        self.host_timer = QTimer(self)
        self.host_timer.timeout.connect(self._check_host_window)

        # Initial Setup
        self.start_mascot()

    def _apply_win32_border_fix(self):
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            dwmapi = ctypes.WinDLL("dwmapi")

            # DWM Constants
            DWMWA_NCRENDERING_POLICY = 2
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMNCRP_DISABLED = 1
            DWMWCP_DONOTROUND = 1

            # 1. Disable Rounded Corners (Windows 11+)
            corner_preference = wintypes.DWORD(DWMWCP_DONOTROUND)
            dwmapi.DwmSetWindowAttribute(
                hwnd, 
                DWMWA_WINDOW_CORNER_PREFERENCE, 
                ctypes.byref(corner_preference), 
                ctypes.sizeof(corner_preference)
            )
            
            # 2. Disable Shadow (Non-client rendering policy)
            rendering_policy = wintypes.DWORD(DWMNCRP_DISABLED)
            dwmapi.DwmSetWindowAttribute(
                hwnd, 
                DWMWA_NCRENDERING_POLICY, 
                ctypes.byref(rendering_policy), 
                ctypes.sizeof(rendering_policy)
            )

            # Standard Win32 Style Cleanup
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_BORDER = 0x00800000
            WS_EX_APPWINDOW = 0x00040000

            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_BORDER)
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)

            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style &= ~WS_EX_APPWINDOW
            # Add WS_EX_LAYERED (0x80000) for transparency support
            ex_style |= 0x00080000 
            
            # Add/Remove WS_EX_TRANSPARENT (0x20) based on current state
            if not self.is_clickable:
                ex_style |= 0x00000020
            else:
                ex_style &= ~0x00000020
                
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

            # Force refresh
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED)

    def start_mascot(self):
        self.update_position()
        self.scheduler.force_behavior("sitting")
        QTimer.singleShot(2000, self.scheduler.start)
        self.show()
        # Apply Win32 border fix after window is shown (winId is valid after show)
        QTimer.singleShot(0, self._apply_win32_border_fix)

    def on_behavior_changed(self, name):
        """Update offsets and handle roaming logic."""
        if name == "leg_hanging":
            self.behavior_y_offset = 15
        elif name in ["pulling"]:
            self.behavior_y_offset = 15
        else:
            self.behavior_y_offset = 0

        # Roaming Logic: If idle and scheduler picks "walk", start roaming
        if name == "walk" and not self.dragging and not self.fall_timer.isActive() and not self.host_hwnd:
            if not getattr(self, "_is_roaming", False):
                QTimer.singleShot(100, self._start_roaming)

        # Reposition window if not dragging, falling, or docked
        if not self.dragging and not self.fall_timer.isActive() and not self.host_hwnd:
            geom = self.screen().availableGeometry()
            target_y = geom.bottom() - self.height() + self.behavior_y_offset
            self._apply_position_clamping(QPoint(self.x(), target_y))

    def _start_roaming(self):
        """Idle behavior: roam away (walk then run), then return."""
        if getattr(self, "_is_roaming", False): return
        self._is_roaming = True
        
        geom = self.screen().availableGeometry()
        roam_dist = random.randint(150, 400)
        direction = 1 if self.x() < geom.center().x() else -1
        
        walk_target = self.x() + (direction * roam_dist * 0.3)
        run_target = self.x() + (direction * roam_dist)
        
        # Clamp to current screen bounds
        walk_target = max(geom.left() + 20, min(walk_target, geom.right() - self.width() - 20))
        run_target = max(geom.left() + 20, min(run_target, geom.right() - self.width() - 20))

        def on_run_finished():
            self.scheduler.force_behavior("stop_run")
            QTimer.singleShot(1500, self._return_to_anchor)

        def start_running():
            self.walk_to(run_target, on_run_finished, speed=10, state="run")

        def pre_run_transition():
            self.scheduler.force_behavior("run_transition")
            QTimer.singleShot(600, start_running)
            
        self.walk_to(walk_target, pre_run_transition, speed=4, state="walk")

    def _return_to_anchor(self):
        """Return home: walk then run back."""
        mid_x = self.x() + (self.anchor_x - self.x()) * 0.3
        
        def finish_home():
            self.scheduler.force_behavior("stop_run")
            QTimer.singleShot(1000, self._on_roaming_finished)
             
        def start_running():
            self.walk_to(self.anchor_x, finish_home, speed=11, state="run")

        def pre_run_transition():
            self.scheduler.force_behavior("run_transition")
            QTimer.singleShot(600, start_running)
            
        self.walk_to(mid_x, pre_run_transition, speed=5, state="walk")

    def _on_roaming_finished(self):
        self._is_roaming = False
        self.scheduler.start()

    # -- file drops --------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return

    def set_frame(self, pixmap):
        if pixmap.isNull(): return
        scaled = pixmap.scaled(self.MASCOT_SIZE, self.MASCOT_SIZE, 
                              Qt.AspectRatioMode.KeepAspectRatio, 
                              Qt.TransformationMode.SmoothTransformation)
        if self.current_direction == "right":
            scaled = scaled.transformed(QTransform().scale(-1, 1))
        self.label.setPixmap(scaled)

    def check_modifier_key(self):
        ctrl_held = bool(QGuiApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl_held != self.is_clickable:
            self.is_clickable = ctrl_held
            # Use native toggle to avoid Qt window recreation flicker
            self._set_native_clickthrough(not ctrl_held)

    def _set_native_clickthrough(self, transparent):
        if sys.platform == "win32":
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            
            user32 = ctypes.windll.user32
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if transparent:
                ex_style |= WS_EX_TRANSPARENT
            else:
                ex_style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            
            # Force refresh of window styles without repositioning or resizing
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.moved.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._undock(fall=False)
            self.key_check_timer.stop()
            self.dragging = True
            self.is_falling = False # Reset falling state if caught
            self.drag_start_pos = event.globalPosition().toPoint()
            self.last_mouse_pos = event.globalPosition().toPoint()
            self.relative_drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

            self._shake_reversals = []
            self._last_shake_sign = None
            self._shake_active = False

            self.scheduler.stop()
            self.fall_timer.stop()
            if hasattr(self, "_move_timer"): self._move_timer.stop()
            self._is_roaming = False
            
            self._show_static_frame("drag", "drag_holding.png")
            self.drag_still_timer.start(300)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            current_pos = event.globalPosition().toPoint()
            dx = current_pos.x() - self.last_mouse_pos.x()
            
            new_pos = current_pos - self.relative_drag_pos
            self._apply_position_clamping(new_pos)

            if abs(dx) > 3:
                self._track_shake(dx)
                self.drag_still_timer.stop()
                self.current_direction = "left" if dx < 0 else "right"
                self._show_static_frame("drag", "dragging_left.png" if dx < 0 else "dragging_right.png")
            elif not self.drag_still_timer.isActive():
                self.drag_still_timer.start(300)
                self._show_static_frame("drag", "drag_holding.png")

            self.last_mouse_pos = current_pos
            event.accept()

    def _track_shake(self, dx):
        """Shake = N fast direction-reversals within a short window, not just any drag."""
        now = time.time() * 1000
        sign = 1 if dx > 0 else -1
        if self._last_shake_sign is not None and sign != self._last_shake_sign:
            self._shake_reversals.append(now)
        self._last_shake_sign = sign

        window_ms = 700
        self._shake_reversals = [t for t in self._shake_reversals if now - t <= window_ms]

        threshold = self.config.get("shake_reversal_threshold") if self.config else 4
        if not self._shake_active and len(self._shake_reversals) >= threshold:
            self._shake_active = True
            self.shake_detected.emit()

    def _apply_position_clamping(self, target_pos):
        geom = self.screen().availableGeometry()
        max_y = geom.bottom() - self.height() + self.behavior_y_offset
        clamped_x = max(geom.left(), min(target_pos.x(), geom.right() - self.width()))
        clamped_y = max(geom.top(), min(target_pos.y(), max_y))
        
        if clamped_x < geom.left() + 50: self.current_direction = "right"
        elif clamped_x > geom.right() - self.width() - 50: self.current_direction = "left"
        
        self.move(clamped_x, clamped_y)

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            self.drag_still_timer.stop()
            self.key_check_timer.start(100)
            
            move_dist = (event.globalPosition().toPoint() - self.drag_start_pos).manhattanLength()
            if move_dist < 5:
                self._handle_click()
            else:
                host_hwnd = self._find_host_window()
                if host_hwnd:
                    self._dock_to_window(host_hwnd)
                else:
                    self.is_falling = True
                    self._start_fall()

            if self._shake_active:
                grace_ms = self.config.get("shake_grace_period_ms") if self.config else 1200
                QTimer.singleShot(grace_ms, self._resolve_shake)

            event.accept()

    def _resolve_shake(self):
        self._shake_active = False
        self.shake_resolved.emit()

    def _start_fall(self):
        """Visual fall with distance-based frame cycling."""
        self.drop_frames_cycled = 0
        self.fall_timer.start(10)

    def _fall_step(self):
        geom = self.screen().availableGeometry()
        ground_y = geom.bottom() - self.height() + self.behavior_y_offset
        dist_remaining = ground_y - self.y()
        
        if dist_remaining > 5:
            new_y = min(self.y() + 8, ground_y)
            self.move(self.x(), new_y)
            
            frame_num = (self.drop_frames_cycled // 8) % 3 + 1
            self._show_static_frame("drop", f"drop_{frame_num}.png")
            self.drop_frames_cycled += 1
            
            if dist_remaining < 20:
                self._show_static_frame("drop", "drop_end.png")
        else:
            self.fall_timer.stop()
            # Show landing frame for a moment before sleeping
            self._show_static_frame("drop", "drop_end.png")
            QTimer.singleShot(500, self._on_landed)

    def _on_landed(self):
        """Transition to sleep after landing. Roaming logic will return her to corner later."""
        if self.dragging: return # Don't sleep if we were caught mid-air
        
        self.is_falling = False
        self.scheduler.force_behavior("sleeping")
        
        # Stay sleeping for a while (10s) then let the scheduler resume normal rotation.
        # If she is far from her side, the next walk will trigger the auto-return roaming.
        QTimer.singleShot(10000, lambda: self.scheduler.start() if not self.dragging else None)


    def _find_host_window(self):
        """Find a visible app window under Miku to perch on."""
        if sys.platform != "win32":
            return None
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        my_hwnd = int(self.winId())
        check_x = self.x() + self.MASCOT_SIZE // 2
        check_y = self.y() + self.height()
        screen = self.screen().availableGeometry()
        excluded = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd")
        GWL_STYLE = -16
        WS_MINIMIZE = 0x20000000

        pt = wintypes.POINT(check_x, check_y)
        hwnd = user32.WindowFromPoint(pt)

        while hwnd:
            root = user32.GetAncestor(hwnd, 2)
            if root != my_hwnd:
                rect = wintypes.RECT()
                user32.GetWindowRect(root, ctypes.byref(rect))
                if (rect.left <= check_x <= rect.right and rect.top <= check_y <= rect.bottom
                        and user32.IsWindowVisible(root)):
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(root, buf, 256)
                    if buf.value not in excluded:
                        style = user32.GetWindowLongW(root, GWL_STYLE)
                        if not (style & WS_MINIMIZE):
                            if rect.top - self.height() >= screen.top():
                                return root
            hwnd = user32.GetWindow(hwnd, 2)

        return None

    def _dock_to_window(self, hwnd):
        """Perch Miku on top of the given host window."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        target_y = rect.top - self.height()
        self.host_offset_x = self.x() - rect.left
        self.host_offset_y = target_y - rect.top

        self.move(self.x(), target_y)
        self.host_hwnd = hwnd
        self.host_timer.start(200)
        self.scheduler.start()

    def _check_host_window(self):
        """Poll the host window: follow its movement, fall if gone."""
        if not self.host_hwnd:
            return
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        if not user32.IsWindow(self.host_hwnd):
            self.scheduler.stop()
            self.host_hwnd = None
            self.host_timer.stop()
            QTimer.singleShot(600, self._delayed_fall_after_close)
            return

        if not user32.IsWindowVisible(self.host_hwnd):
            self.scheduler.stop()
            self.host_hwnd = None
            self.host_timer.stop()
            QTimer.singleShot(600, self._delayed_fall_after_close)
            return

        GWL_STYLE = -16
        WS_MINIMIZE = 0x20000000
        style = user32.GetWindowLongW(self.host_hwnd, GWL_STYLE)
        if style & WS_MINIMIZE:
            self.scheduler.stop()
            self.host_hwnd = None
            self.host_timer.stop()
            QTimer.singleShot(600, self._delayed_fall_after_close)
            return

        rect = wintypes.RECT()
        user32.GetWindowRect(self.host_hwnd, ctypes.byref(rect))

        # Fall if window shrank and Miku is no longer over it
        feet_x = rect.left + self.host_offset_x + self.MASCOT_SIZE // 2
        if feet_x < rect.left - 10 or feet_x > rect.right + 10:
            self._undock(fall=True)
            return

        if rect.top >= self.y() + self.height():
            self._undock(fall=True)
            return

        target_x = rect.left + self.host_offset_x
        target_y = rect.top + self.host_offset_y
        self.move(target_x, target_y)

    def _delayed_fall_after_close(self):
        """Fall after host window disappears."""
        if self.host_hwnd or self.dragging:
            return
        self.scheduler.stop()
        self.is_falling = True
        self._start_fall()

    def _undock(self, fall=True):
        """Detach from host window, optionally fall."""
        if self.host_hwnd:
            self.host_hwnd = None
            self.host_timer.stop()
            self.host_offset_x = 0
            self.host_offset_y = 0
            self.scheduler.stop()
            if fall:
                self.is_falling = True
                self._start_fall()

    def _return_to_nearest_corner(self):
        """Homing: walk then run back."""
        geom = self.screen().availableGeometry()
        dist_left = self.x() - geom.left()
        dist_right = geom.right() - self.width() - self.x()
        
        target_x = geom.left() + 20 if dist_left < dist_right else geom.right() - self.width() - 50
        self.anchor_x = target_x
        
        mid_x = self.x() + (target_x - self.x()) * 0.3
        
        def finish_homing():
            self.scheduler.force_behavior("stop_run")
            QTimer.singleShot(1000, lambda: self.scheduler.start())
             
        def start_running():
            self.walk_to(target_x, finish_homing, speed=10, state="run")

        def pre_run_transition():
            self.scheduler.force_behavior("run_transition")
            QTimer.singleShot(600, start_running)
            
        self.walk_to(mid_x, pre_run_transition, speed=5, state="walk")

    def _on_drag_still(self):
        self.drag_still_timer.start(1000)
        curr = getattr(self, "_last_drag_frame", "drag_holding.png")
        next_f = "drag_holding_2.png" if curr == "drag_holding.png" else "drag_holding.png"
        self._show_static_frame("drag", next_f)
        self._last_drag_frame = next_f

    def _handle_click(self):
        choice = random.choice(["pulling", "wondering_left", "smirking"])
        if choice == "wondering_left":
            self.scheduler.force_behavior("wondering_left")
            QTimer.singleShot(1000, lambda: self.scheduler.force_behavior("wondering_right"))
        else:
            self.scheduler.force_behavior(choice)

    def start_wake_up_sequence(self):
        self.scheduler.stop()
        self.scheduler.force_behavior("pulling")
        def walk_away():
            target_x = self.x() - 150
            geom = self.screen().availableGeometry()
            target_x = max(geom.left() + 20, target_x)
            self.walk_to(target_x, walk_back)
        def walk_back():
            self.walk_to(self.anchor_x, lambda: self.scheduler.start())
        QTimer.singleShot(1500, walk_away)

    def _show_static_frame(self, subdir, filename):
        path = os.path.join(self.scheduler.assets_dir, subdir, filename)
        if os.path.exists(path):
            self.set_frame(QPixmap(path))

    def update_position(self):
        geom = self.screen().availableGeometry()
        self.anchor_x = geom.right() - self.width() - 50
        self.move(self.anchor_x, geom.bottom() - self.height())

    def set_state(self, state, direction="left"):
        self.current_direction = direction
        if state == "idle": self.scheduler.start()
        else: self.scheduler.force_behavior(state)

    def walk_to(self, target_x, callback=None, speed=5, state="walk"):
        # CLAMP target_x to screen bounds to avoid infinite walk loops at edges
        geom = self.screen().availableGeometry()
        min_x = geom.left()
        max_x = geom.right() - self.width()
        self.target_x = max(min_x, min(int(target_x), max_x))
        
        self.move_callback = callback
        self.current_direction = "left" if self.target_x < self.x() else "right"
        self.scheduler.force_behavior(state)
        
        if hasattr(self, "_move_timer") and self._move_timer.isActive():
            self._move_timer.stop()
        self._move_timer = QTimer()
        self._move_timer.timeout.connect(lambda: self._move_step(int(speed)))
        self._move_timer.start(20)

    def reset_roaming(self):
        """Forcefully stop roaming sequence. Does NOT restart scheduler to avoid race conditions."""
        self._is_roaming = False
        self.dragging = False
        if hasattr(self, "_move_timer"):
            self._move_timer.stop()
        self.scheduler.stop()

    def _move_step(self, speed):
        if abs(self.x() - self.target_x) <= speed:
            self.move(self.target_x, self.y())
            self._move_timer.stop()
            if self.move_callback: self.move_callback()
        else:
            prev_x = self.x()
            self.move(self.x() + (speed if self.target_x > self.x() else -speed), self.y())
            
            # Safety: If move failed (stuck at edge or OS-blocked), stop walking
            if self.x() == prev_x:
                self._move_timer.stop()
                if self.move_callback: self.move_callback()


    def start_dialog_mode(self):
        self.scheduler.start_dialog_animation()

    def stop_dialog_mode(self):
        self.scheduler.stop_dialog_animation()

    def knock_sequence(self, callback=None):
        self.start_dialog_mode()
        QTimer.singleShot(2000, lambda: callback() if callback else None)

    def update_timer_display(self, total_seconds):
        try:
            # Clamp to reasonable range (0 to 24 hours) to prevent "weird long numbers"
            total_seconds = max(0, min(int(total_seconds), 86400))
            mins = total_seconds // 60
            secs = total_seconds % 60
            self.timer_label.setText(f"{mins:02d}:{secs:02d}")
        except Exception:
            self.timer_label.setText("--:--")

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = MascotWindow()
    sys.exit(app.exec())