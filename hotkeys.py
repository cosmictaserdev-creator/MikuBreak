"""Global hotkeys via RegisterHotKey + QAbstractNativeEventFilter.

Activation: RegisterHotKey (OS-level, event-driven, zero polling).
Release:    lightweight GetAsyncKeyState polling (only while key is held).

pynput's GlobalHotKeys can't match Ctrl+Alt+letter combos — Windows maps
the letter through AltGr character translation and the combo never fires.
RegisterHotKey sidesteps this entirely: the OS matches raw VK codes."""

import ctypes
import ctypes.wintypes

from PyQt6.QtCore import (
    QObject, QTimer, QAbstractNativeEventFilter, QCoreApplication, pyqtSignal,
)

# ── VK code map ──────────────────────────────────────────────────────────────

VK_MAP = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "meta": 0x5B,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
}

MODIFIER_VKS = {0x11, 0x12, 0x10, 0x5B}  # ctrl, alt, shift, win

MOD_MAP = {
    0x11: 0x0002,  # ctrl  -> MOD_CONTROL
    0x12: 0x0001,  # alt   -> MOD_ALT
    0x10: 0x0004,  # shift -> MOD_SHIFT
    0x5B: 0x0008,  # win   -> MOD_WIN
}

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [
    ctypes.wintypes.HWND, ctypes.c_int,
    ctypes.wintypes.UINT, ctypes.wintypes.UINT,
]
_user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL


# ── Combo parsing ────────────────────────────────────────────────────────────

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


def _parse_vk_combo(combo: str) -> tuple[int, int]:
    """'<ctrl>+<alt>+v' -> (MOD_CONTROL | MOD_ALT, 0x56).
    Returns (0, 0) for invalid/empty combos."""
    mods = 0
    vk = 0
    for part in (combo or "").replace("<", "").replace(">", "").split("+"):
        part = part.strip().lower()
        if part in VK_MAP:
            vk_code = VK_MAP[part]
            if vk_code in MOD_MAP:
                mods |= MOD_MAP[vk_code]
            else:
                vk = vk_code
        elif len(part) == 1 and (part.isalpha() or part.isdigit()):
            vk = ord(part.upper())
    if not vk or not mods:
        return 0, 0
    return mods, vk


# ── Singleton hotkey filter (WM_HOTKEY receiver) ─────────────────────────────

class _HotkeyFilter(QAbstractNativeEventFilter):
    """Intercepts WM_HOTKEY from the OS and dispatches to registered callbacks.
    Install once on QCoreApplication — all HotkeyPoller instances share it."""

    def __init__(self):
        super().__init__()
        self._callbacks: dict[int, callable] = {}
        self._next_id = 1

    def allocate_id(self) -> int:
        hid = self._next_id
        self._next_id += 1
        return hid

    def register(self, hotkey_id: int, combo: str, callback: callable) -> bool:
        self.unregister(hotkey_id)
        mods, vk = _parse_vk_combo(combo)
        if not mods:
            return False
        ok = bool(_user32.RegisterHotKey(0, hotkey_id, mods | MOD_NOREPEAT, vk))
        if ok:
            self._callbacks[hotkey_id] = callback
        return ok

    def unregister(self, hotkey_id: int):
        _user32.UnregisterHotKey(0, hotkey_id)
        self._callbacks.pop(hotkey_id, None)

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            addr = int(message)
            msg = ctypes.wintypes.MSG.from_address(addr)
            if msg.message == WM_HOTKEY:
                cb = self._callbacks.get(msg.wParam)
                if cb:
                    cb()
                    return True, 0
        return False, 0


_filter_instance: _HotkeyFilter | None = None


def _get_filter() -> _HotkeyFilter:
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = _HotkeyFilter()
        QCoreApplication.instance().installNativeEventFilter(_filter_instance)
    return _filter_instance


# ── Public API ───────────────────────────────────────────────────────────────

class HotkeyPoller(QObject):
    """Event-driven press (RegisterHotKey) + lightweight release polling.

    Signals are identical to the old polling-only version — drop-in replacement.
    Press is instant (OS dispatches WM_HOTKEY). Release is detected at 15 ms
    intervals only while the key is held (zero CPU cost when idle)."""

    pressed = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, combo: str, interval_ms: int = 15):
        super().__init__()
        self._vks = parse_combo(combo)
        self._combo = combo
        self._down = False
        self._hotkey_id = _get_filter().allocate_id()
        self._skip_next = False

        self._release_timer = QTimer(self)
        self._release_timer.setInterval(interval_ms)
        self._release_timer.timeout.connect(self._check_release)

    def start(self):
        if not self._vks:
            return
        _get_filter().register(self._hotkey_id, self._combo, self._on_press)

    def stop(self):
        self._release_timer.stop()
        _get_filter().unregister(self._hotkey_id)
        if self._down:
            self._down = False
            self.released.emit()

    def update_combo(self, combo: str):
        was_running = self._down or self._release_timer.isActive()
        self.stop()
        self._vks = parse_combo(combo)
        self._combo = combo
        if was_running:
            self.start()

    def _on_press(self):
        if self._down:
            return
        self._down = True
        self._skip_next = True
        self._release_timer.start()
        self.pressed.emit()

    def _check_release(self):
        if self._skip_next:
            self._skip_next = False
            return
        user32 = ctypes.windll.user32
        down = all(user32.GetAsyncKeyState(vk) & 0x8000 for vk in self._vks)
        if not down:
            self._release_timer.stop()
            self._down = False
            self.released.emit()


if __name__ == "__main__":
    assert parse_combo("<ctrl>+<alt>+d") == {0x11, 0x12, 0x44}
    assert parse_combo("<ctrl>+<shift>+9") == {0x11, 0x10, ord("9")}
    assert parse_combo("") == set()
    assert parse_combo("<ctrl>+<bogus>") == set()
    assert parse_combo("<ctrl>+<shift>") == set()

    assert _parse_vk_combo("<ctrl>+<alt>+d") == (0x0002 | 0x0001, 0x44)
    assert _parse_vk_combo("<ctrl>+<alt>+v") == (0x0002 | 0x0001, 0x56)
    assert _parse_vk_combo("") == (0, 0)
    assert _parse_vk_combo("<ctrl>") == (0, 0)

    print("hotkeys: all checks passed")
