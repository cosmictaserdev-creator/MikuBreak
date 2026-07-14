from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPen

# ponytail: no dedicated "pointing" sprite art exists yet — an on-screen ring marker
# stands in for the animated point gesture the spec describes. Swap in real point
# frames + drop the marker once art exists.


class PointMarker(QWidget):
    RADIUS = 22

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._label_text = ""
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_at(self, x, y, label="", duration_ms=5000):
        self._label_text = label
        w = self.RADIUS * 2 + 22
        h = self.RADIUS * 2 + (50 if label else 22)
        screen = self.screen().availableGeometry()
        left = max(screen.left(), min(x - self.RADIUS - 10, screen.right() - w))
        top = max(screen.top(), min(y - self.RADIUS - 10, screen.bottom() - h))
        self.setGeometry(left, top, w, h)
        self.show()
        self.raise_()
        self.update()
        self._hide_timer.start(duration_ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#8387c4"))
        pen.setWidth(4)
        painter.setPen(pen)
        painter.drawEllipse(10, 10, self.RADIUS * 2, self.RADIUS * 2)
        if self._label_text:
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                QRect(10, self.RADIUS * 2 + 14, 240, 30),
                Qt.AlignmentFlag.AlignLeft,
                self._label_text,
            )
