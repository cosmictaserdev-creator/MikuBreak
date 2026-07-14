"""VK-polling global hotkeys. pynput's GlobalHotKeys can't match combos like
<ctrl>+<alt>+d — with Ctrl+Alt held, Windows maps the letter to no character, pynput
sees a raw keycode and the combo never fires. Polling GetAsyncKeyState on the parsed
virtual keys sidesteps character mapping entirely and runs on the GUI thread."""

import ctypes

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

VK_MAP = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "meta": 0x5B,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
}


MODIFIER_VKS = {0x11, 0x12, 0x10, 0x5B}  # ctrl, alt, shift, win


def parse_combo(combo: str) -> set[int]:
    """'<ctrl>+<alt>+d' -> {0x11, 0x12, 0x44}. Unknown keys are skipped.
    Returns empty set if the combo has no non-modifier key (prevents accidental triggers)."""
    vks = set()
    for part in (combo or "").replace("<", "").replace(">", "").split("+"):
        part = part.strip().lower()
        if part in VK_MAP:
            vks.add(VK_MAP[part])
        elif len(part) == 1 and (part.isalpha() or part.isdigit()):
            vks.add(ord(part.upper()))
    if vks and not (vks - MODIFIER_VKS):
        return set()  # modifier-only combo — ignore to avoid accidental triggers
    return vks


class HotkeyPoller(QObject):
    """Emits pressed on the rising edge of all combo keys held, released on the
    falling edge. Runs entirely on the GUI thread — safe to touch widgets/timers."""

    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, combo: str, interval_ms: int = 40):
        super().__init__()
        self._vks = parse_combo(combo)
        self._down = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._check)

    def start(self):
        if self._vks:
            self._timer.start()

    def stop(self):
        self._timer.stop()
        if self._down:
            self._down = False
            self.released.emit()

    def _check(self):
        user32 = ctypes.windll.user32
        down = all(user32.GetAsyncKeyState(vk) & 0x8000 for vk in self._vks)
        if down and not self._down:
            self._down = True
            self.pressed.emit()
        elif not down and self._down:
            self._down = False
            self.released.emit()


if __name__ == "__main__":
    assert parse_combo("<ctrl>+<alt>+d") == {0x11, 0x12, 0x44}
    assert parse_combo("<ctrl>+<shift>+9") == {0x11, 0x10, ord("9")}
    assert parse_combo("") == set()
    assert parse_combo("<ctrl>+<bogus>") == set()  # modifier-only after unknown key is skipped
    assert parse_combo("<ctrl>+<shift>") == set()  # modifier-only combos rejected
    print("hotkeys: parse_combo checks passed")
