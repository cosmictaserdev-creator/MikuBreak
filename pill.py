import math
import sys

from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap

AMPLITUDE_BARS = 9

BUBBLE_FONT = "'DM Serif Display', serif"


def _read_linger_ms(text: str) -> int:
    return max(3000, min(12000, len(text) * 60))


class _InputEdit(QTextEdit):
    """Auto-growing input box. Enter submits, Shift+Enter inserts newline, Esc closes."""

    submitted = pyqtSignal(str)
    escaped = pyqtSignal()
    typed = pyqtSignal()

    MIN_HEIGHT = 38
    MAX_HEIGHT = 92  # ~3 lines, then internal scroll

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Ask Miku...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(self.MIN_HEIGHT)
        self.setStyleSheet(f"""
            QTextEdit {{
                color: #FFFFFF;
                background-color: rgba(26, 33, 56, 255);
                border: none;
                border-radius: 12px;
                padding: 6px 10px;
                font-size: 14px;
                font-family: {BUBBLE_FONT};
            }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: #8387c4; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.textChanged.connect(self._grow)
        self.textChanged.connect(self.typed.emit)

    def _grow(self):
        doc_h = int(self.document().size().height()) + 14
        self.setFixedHeight(max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, doc_h)))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                text = self.toPlainText().strip()
                self.clear()
                if text:
                    self.submitted.emit(text)
        elif event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
        else:
            super().keyPressEvent(event)


class MikuPill(QWidget):
    """Single floating widget, bottom-anchored to the same spot the mascot's original
    small countdown bubble occupied. Morphs between:
    idle (countdown pill) -> listening (live mic amplitude bars) / thinking (pulse dots)
    -> chat (a full chat thread with bubbles + growing input box) -- then back to idle."""

    submitted = pyqtSignal(str)

    ANCHOR_Y_OFFSET = 27  # matches the original embedded timer_label's bottom edge (3px inset + 24px tall)
    IDLE_WIDTH = 90
    IDLE_HEIGHT = 28
    MID_HEIGHT = 44  # listening / thinking
    LISTEN_WIDTH = 150
    CHAT_WIDTH = 380
    CHAT_MIN_HEIGHT = 170
    CHAT_MAX_HEIGHT = 420
    DISMISS_MS = 25000  # idle timeout while chat is pinned open

    def __init__(self, mascot):
        super().__init__()
        self.mascot = mascot

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._mode = "idle"  # "idle" | "listening" | "thinking" | "chat"
        self._chat_pinned = False  # True when the user opened/engaged the panel
        self._countdown_text = "--:--"
        self._amplitude_levels = [0.0] * AMPLITUDE_BARS
        self._phase = 0.0
        self._last_reply = ""

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._build_chat_area()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.close_chat)

        self.mascot.moved.connect(self._follow_mascot)  # reposition the instant she moves, not on a poll delay

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_animation)
        self._anim_timer.start(60)

        self.resize(self.IDLE_WIDTH, self.IDLE_HEIGHT)
        self._follow_mascot()
        self.show()
        QTimer.singleShot(0, self._apply_win32_style)

    # -- chat panel construction --------------------------------------------------

    def _build_chat_area(self):
        self._chat_area = QWidget(self)
        self._chat_area.hide()

        layout = QVBoxLayout(self._chat_area)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: #8387c4; border-radius: 3px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._messages = QWidget()
        self._messages_layout = QVBoxLayout(self._messages)
        self._messages_layout.setContentsMargins(0, 0, 4, 0)
        self._messages_layout.setSpacing(6)
        self._messages_layout.addStretch(1)  # keeps bubbles bottom-anchored while few
        self._scroll.setWidget(self._messages)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: #8387c4; font-size: 12px; font-family: {BUBBLE_FONT}; background: transparent;"
        )
        self._status.hide()

        self._input = _InputEdit()
        self._input.submitted.connect(self._on_input_submitted)
        self._input.escaped.connect(self.close_chat)
        self._input.typed.connect(self._touch)

        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._status)
        layout.addWidget(self._input)

    def _add_bubble(self, text, from_user, pixmap=None):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        label = QLabel(text)
        row._bubble_label = label  # streaming updates need a handle to the label
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMaximumWidth(int(self.CHAT_WIDTH * 0.75))

        if pixmap is not None:
            # bubble with a thumbnail above the text (screen-guide answers)
            bubble = QWidget()
            bubble.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            bubble.setStyleSheet("background-color: #1a2138; border-radius: 12px;")
            v = QVBoxLayout(bubble)
            v.setContentsMargins(7, 7, 7, 7)
            v.setSpacing(6)
            img = QLabel()
            img.setPixmap(pixmap)
            img.setStyleSheet("background: transparent;")
            v.addWidget(img)
            label.setStyleSheet(f"""
                background: transparent; color: #FFFFFF; padding: 0 4px 4px 4px;
                font-size: 14px; font-family: {BUBBLE_FONT};
            """)
            v.addWidget(label)
            h.addWidget(bubble)
            h.addStretch(1)
        elif from_user:
            label.setStyleSheet(f"""
                background-color: #8387c4; color: #0a1123;
                border-radius: 12px; padding: 7px 11px;
                font-size: 14px; font-family: {BUBBLE_FONT};
            """)
            h.addStretch(1)
            h.addWidget(label)
        else:
            label.setStyleSheet(f"""
                background-color: #1a2138; color: #FFFFFF;
                border-radius: 12px; padding: 7px 11px;
                font-size: 14px; font-family: {BUBBLE_FONT};
            """)
            h.addWidget(label)
            h.addStretch(1)

        self._messages_layout.addWidget(row)
        QTimer.singleShot(0, self._scroll_to_bottom)
        if self._mode == "chat":
            self._resize_to(self.CHAT_WIDTH, self._chat_target_height())
        return row

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _chat_target_height(self):
        chrome = 12 + 12 + 8 + self._input.height()  # margins + spacing + input
        if not self._status.isHidden():
            chrome += self._status.sizeHint().height() + 8
        content = self._messages_layout.sizeHint().height() + chrome + 16
        return max(self.CHAT_MIN_HEIGHT, min(self.CHAT_MAX_HEIGHT, content))

    # -- win32 / click-through -----------------------------------------------------

    def _apply_win32_style(self):
        if sys.platform == "win32":
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            user32 = ctypes.windll.user32
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED)

    def _set_click_through(self, enabled):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if sys.platform == "win32":
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            user32 = ctypes.windll.user32
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex = (ex | WS_EX_TRANSPARENT) if enabled else (ex & ~WS_EX_TRANSPARENT)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

    # -- geometry ------------------------------------------------------------------

    def _clamp_x(self, x, width):
        geom = self.mascot.screen().availableGeometry()
        return max(geom.left(), min(x, geom.right() - width))

    def _follow_mascot(self):
        if self._anim.state() == QPropertyAnimation.State.Running:
            return
        pos = self.mascot.pos()
        target_x = self._clamp_x(pos.x() + self.mascot.width() // 2 - self.width() // 2, self.width())
        target_y = pos.y() + self.ANCHOR_Y_OFFSET - self.height()
        self.move(target_x, target_y)

    def _resize_to(self, width, height):
        pos = self.mascot.pos()
        target_x = self._clamp_x(pos.x() + self.mascot.width() // 2 - width // 2, width)
        target_y = pos.y() + self.ANCHOR_Y_OFFSET - height
        target = QRect(target_x, target_y, width, height)

        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def resizeEvent(self, event):
        self._chat_area.setGeometry(self.rect())
        super().resizeEvent(event)

    def _tick_animation(self):
        self._phase += 1
        if self._mode in ("listening", "thinking"):
            self.update()
        elif self._mode == "chat" and not self._status.isHidden():
            dots = "." * (1 + int(self._phase / 6) % 3)
            self._status.setText(self._status_base + dots)

    # -- state transitions --------------------------------------------------------

    def show_countdown(self, seconds_remaining: int):
        mins, secs = divmod(max(0, int(seconds_remaining)), 60)
        self._countdown_text = f"{mins:02d}:{secs:02d}"
        if self._mode == "idle":
            self.update()

    def start_listening(self):
        if self._mode == "chat":
            self._set_status("listening")
            return
        self._mode = "listening"
        self._amplitude_levels = [0.0] * AMPLITUDE_BARS
        self._resize_to(self.LISTEN_WIDTH, self.MID_HEIGHT)

    def update_amplitude(self, level: float):
        """level: 0.0-1.0 RMS from the mic, fed live while recording."""
        if self._mode != "listening":
            return
        self._amplitude_levels.append(max(0.0, min(1.0, level)))
        self._amplitude_levels = self._amplitude_levels[-AMPLITUDE_BARS:]
        self.update()

    def start_thinking(self):
        if self._mode == "chat":
            self._set_status("thinking")
            return
        self._mode = "thinking"
        self._resize_to(self.IDLE_WIDTH, self.MID_HEIGHT)

    _status_base = ""

    def _set_status(self, text):
        self._status_base = text
        if text:
            self._status.setText(text)
            self._status.show()
        else:
            self._status.hide()

    # -- chat panel API -------------------------------------------------------------

    def open_chat(self, pinned=True):
        self._chat_pinned = self._chat_pinned or pinned
        if self._mode == "chat":
            if pinned:
                self._focus_input()
                self._touch()
            return
        self._mode = "chat"
        self._set_click_through(False)
        self._chat_area.show()
        self._resize_to(self.CHAT_WIDTH, self._chat_target_height())
        self.update()
        if pinned:
            self._focus_input()
            self._touch()

    def _focus_input(self):
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def close_chat(self):
        self._dismiss_timer.stop()
        self._chat_pinned = False
        if self._mode != "chat":
            return
        self._set_status("")
        self._input.clear()
        self._chat_area.hide()
        self._set_click_through(True)
        self._mode = "idle"
        self._resize_to(self.IDLE_WIDTH, self.IDLE_HEIGHT)

    def add_user_message(self, text: str):
        self.open_chat(pinned=False)
        self._add_bubble(text, from_user=True)

    def add_miku_message(self, text: str):
        self.open_chat(pinned=False)
        self._set_status("")
        self._last_reply = text
        self._add_bubble(text, from_user=False)

    def _on_input_submitted(self, text):
        self._chat_pinned = True
        self._touch()
        self._add_bubble(text, from_user=True)
        self.submitted.emit(text)

    def _touch(self):
        """Any user interaction restarts the auto-dismiss countdown."""
        self._dismiss_timer.start(self.DISMISS_MS)

    # -- streaming ------------------------------------------------------------------

    _stream_row = None

    def stream_delta(self, text: str):
        """Live token chunks: first chunk creates an empty Miku bubble, the rest append."""
        if self._stream_row is None:
            self.open_chat(pinned=False)
            self._set_status("")
            self._stream_row = self._add_bubble("", from_user=False)
        label = self._stream_row._bubble_label
        label.setText(label.text() + text)
        QTimer.singleShot(0, self._scroll_to_bottom)
        if self._mode == "chat":
            self._resize_to(self.CHAT_WIDTH, self._chat_target_height())

    def reset_stream(self):
        """The streamed text turned out to be a tool-call turn — drop the partial bubble."""
        if self._stream_row is not None:
            self._stream_row.setParent(None)
            self._stream_row.deleteLater()
            self._stream_row = None
        self._set_status("thinking")

    def _finalize_stream(self, text: str) -> bool:
        """Reply arrived: if it streamed in, pin the exact final text on that bubble."""
        if self._stream_row is None:
            return False
        self._stream_row._bubble_label.setText(text)
        self._last_reply = text
        self._stream_row = None
        self._set_status("")
        return True

    # -- compatibility with the old response flow -----------------------------------

    def show_response(self, text: str):
        """Every spoken/typed reply lands here. Streamed replies just get finalized;
        everything else (voice answer, nudge, timer fired, errors) becomes a new bubble,
        auto-opening the panel if it's closed."""
        if not self._finalize_stream(text):
            self.add_miku_message(text)
        if self._chat_pinned:
            self._touch()

    def show_screen_response(self, text: str, image_path: str):
        """Screen-guide answer with a thumbnail of what she looked at."""
        pm = QPixmap(image_path) if image_path else QPixmap()
        if pm.isNull():
            self.show_response(text)
            return
        self.open_chat(pinned=False)
        self._set_status("")
        self._last_reply = text
        thumb = pm.scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
        self._add_bubble(text, from_user=False, pixmap=thumb)
        if self._chat_pinned:
            self._touch()

    def is_idle(self) -> bool:
        return self._mode == "idle"

    def return_to_idle(self):
        """Called when she finishes talking. Pinned chat stays open (idle timeout
        handles it); auto-opened chat lingers briefly so the reply can be read."""
        if self._mode == "chat":
            if self._chat_pinned:
                self._touch()
            else:
                self._dismiss_timer.start(_read_linger_ms(self._last_reply))
            return
        self._mode = "idle"
        self._resize_to(self.IDLE_WIDTH, self.IDLE_HEIGHT)

    # -- painting --------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        painter.setBrush(QColor(0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        radius = min(18 if self._mode == "chat" else 24, rect.height() / 2)
        painter.drawRoundedRect(rect, radius, radius)

        if self._mode == "idle":
            self._paint_idle(painter, rect)
        elif self._mode == "listening":
            self._paint_listening(painter, rect)
        elif self._mode == "thinking":
            self._paint_thinking(painter, rect)
        # chat mode: child widgets paint themselves

    def _paint_idle(self, painter, rect):
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("DM Serif Display", 12))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._countdown_text)

    def _paint_listening(self, painter, rect):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8387c4"))
        n = len(self._amplitude_levels)
        gap = 5
        bar_w = 4
        total_w = n * bar_w + (n - 1) * gap
        start_x = rect.center().x() - total_w // 2
        mid_y = rect.center().y()
        for i, level in enumerate(self._amplitude_levels):
            h = max(4, int(level * (rect.height() - 14)))
            x = start_x + i * (bar_w + gap)
            painter.drawRoundedRect(QRect(x, mid_y - h // 2, bar_w, h), 2, 2)

    def _paint_thinking(self, painter, rect):
        painter.setPen(Qt.PenStyle.NoPen)
        cx = rect.center().x()
        cy = rect.center().y()
        for i in range(3):
            bounce = math.sin(self._phase * 0.3 + i * 1.4) * 4
            alpha = 140 + int(80 * math.sin(self._phase * 0.3 + i * 1.4))
            painter.setBrush(QColor(131, 135, 196, max(80, alpha)))
            x = cx - 20 + i * 20
            painter.drawEllipse(int(x - 4), int(cy - 4 + bounce), 8, 8)
