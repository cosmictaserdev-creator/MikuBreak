import ctypes
import os
import tempfile

import mss
import uiautomation as auto

MAX_ELEMENTS = 60
MAX_DEPTH = 4


def get_foreground_window_title() -> str:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


MAX_SCREENSHOT_WIDTH = 1920  # downscale huge/multi-monitor grabs to keep the vision payload sane


def capture_screenshot() -> str:
    """Screenshots the full virtual screen (all monitors). Returns path to a temp PNG."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with mss.mss() as sct:
        img = sct.grab(sct.monitors[0])  # monitors[0] = entire virtual screen
        mss.tools.to_png(img.rgb, img.size, output=path)

    if img.size.width > MAX_SCREENSHOT_WIDTH:
        # QImage is safe off the GUI thread (no QPixmap involved).
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage
        scaled = QImage(path).scaledToWidth(
            MAX_SCREENSHOT_WIDTH, Qt.TransformationMode.SmoothTransformation
        )
        scaled.save(path, "PNG")
    return path


def get_ui_elements() -> list[dict]:
    """Best-effort flat list of named, visible elements in the foreground window:
    name, control type, and center point. Cheaper and more accurate than vision-guessing
    pixels, per the screen-guide design — used as the primary capture mode."""
    elements = []
    try:
        root = auto.GetForegroundControl()
        if root:
            _walk(root, elements, depth=0)
    except Exception:
        pass
    return elements


def _walk(element, elements, depth):
    if depth > MAX_DEPTH or len(elements) >= MAX_ELEMENTS:
        return
    try:
        if element.Name and element.BoundingRectangle.width() > 0:
            rect = element.BoundingRectangle
            elements.append({
                "name": element.Name,
                "control_type": element.ControlTypeName,
                "x": (rect.left + rect.right) // 2,
                "y": (rect.top + rect.bottom) // 2,
            })
    except Exception:
        pass

    try:
        for child in element.GetChildren():
            _walk(child, elements, depth + 1)
    except Exception:
        pass


def format_ui_elements(elements: list[dict]) -> str:
    if not elements:
        return ""
    lines = [f'- "{e["name"]}" ({e["control_type"]}) at ({e["x"]},{e["y"]})' for e in elements]
    return "Visible UI elements:\n" + "\n".join(lines)
