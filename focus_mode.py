"""Focus sessions: Miku watches the active window and gently calls out distractions.
Started/ended by the LLM tools (start_focus / end_focus / focus_status)."""

import time
from datetime import datetime, timedelta

from PyQt6.QtCore import QObject, QTimer

from brain.tools import _get_active_window

POLL_MS = 15000
NUDGE_COOLDOWN_S = 120


class FocusMode(QObject):
    def __init__(self, config, chat_controller):
        super().__init__()
        self.config = config
        self.chat = chat_controller
        self._end_at = None
        self._started_at = None
        self._minutes = 0
        self._distractions = 0
        self._last_nudge = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._check)

    @property
    def active(self) -> bool:
        return self._end_at is not None

    def start(self, minutes: int):
        self._minutes = max(1, int(minutes))
        self._started_at = datetime.now()
        self._end_at = self._started_at + timedelta(minutes=self._minutes)
        self._distractions = 0
        self._last_nudge = 0.0
        self._timer.start()

    def end(self, early: bool = False):
        if not self.active:
            return
        self._timer.stop()
        elapsed_min = max(1, int((datetime.now() - self._started_at).total_seconds() // 60))
        self._end_at = None
        if early:
            recap = f"Focus session ended early after {elapsed_min} minutes. Distraction moments: {self._distractions}."
        else:
            recap = (f"Focus session complete — {self._minutes} minutes, nice work! "
                     f"Distraction moments: {self._distractions}."
                     + (" Spotless run!" if self._distractions == 0 else ""))
        self.chat._speak_nudge(recap)

    def status(self) -> str:
        """Called from the LLM worker thread — pure reads, safe."""
        if not self.active:
            return "no focus session running"
        remaining = max(0, int((self._end_at - datetime.now()).total_seconds() // 60))
        return f"focus session active: {remaining} minutes left, {self._distractions} distraction moments so far"

    def _check(self):
        if datetime.now() >= self._end_at:
            self.end()
            return
        try:
            title = _get_active_window().lower()
        except Exception:
            return
        for term in self.config.get("focus_blocklist") or []:
            if term.lower() in title:
                self._distractions += 1
                if time.monotonic() - self._last_nudge > NUDGE_COOLDOWN_S:
                    self._last_nudge = time.monotonic()
                    remaining = max(1, int((self._end_at - datetime.now()).total_seconds() // 60))
                    self.chat._speak_nudge(
                        f"Hey — is that {term} I see? {remaining} minutes of focus left, you've got this!"
                    )
                break
