import random
from PyQt6.QtCore import QObject, QTimer

CHATTER_PROMPT = (
    "Share one short, interesting fact or piece of trivia, unprompted — like a friend "
    "mentioning something they just read. If the user's focused window (in your context) "
    "suggests what they're working on, you may riff on that instead — a relevant tidbit "
    "or light encouragement, never a critique. One or two sentences, nothing more."
)

FREQUENCY_MINUTES = {
    "rare": (90, 180),
    "occasional": (45, 90),
    "chatty": (15, 30),
}


class IdleChatter(QObject):
    """Occasionally self-prompts the LLM for a short fact, delivered through the
    normal chat pipeline (pill + voice). Skips a beat if she's already mid-interaction,
    so it never collides with a habit/reminder nudge or an actual conversation."""

    def __init__(self, config, chat_controller):
        super().__init__()
        self.config = config
        self.chat_controller = chat_controller

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fire)

    def start(self):
        self._schedule_next()

    def stop(self):
        self.timer.stop()

    def _schedule_next(self):
        lo, hi = FREQUENCY_MINUTES.get(self.config.get("chatter_frequency"), FREQUENCY_MINUTES["occasional"])
        self.timer.start(int(random.uniform(lo, hi) * 60 * 1000))

    def _fire(self):
        if not self.config.get("chatter_enabled"):
            self._schedule_next()
            return
        if self.chat_controller.mascot.dragging or not self.chat_controller.pill.is_idle():
            self._schedule_next()
            return
        self.chat_controller.handle_prompt(CHATTER_PROMPT)
        self._schedule_next()
