from PyQt6.QtCore import QObject, QTimer

CHECK_INTERVAL_MS = 60_000


class MemoryScheduler(QObject):
    """Checks due reminders and stale habits every 60s, delivers nudges via ChatController."""

    def __init__(self, store, chat_controller):
        super().__init__()
        self.store = store
        self.chat_controller = chat_controller

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check)

    def start(self):
        self.timer.start(CHECK_INTERVAL_MS)

    def stop(self):
        self.timer.stop()

    def _check(self):
        due_reminders = self.store.get_due_reminders()
        if due_reminders:
            reminder = due_reminders[0]  # one nudge at a time
            self.store.complete_or_reschedule_reminder(reminder["id"], reminder["recurring_rule"])
            self.chat_controller.deliver_nudge(reminder["text"])
            return  # don't stack a habit nudge in the same tick

        due_habits = self.store.get_due_habits()
        if due_habits:
            habit = due_habits[0]
            self.store.update_habit_triggered(habit["name"])
            self.chat_controller.deliver_nudge(f"Hey, maybe it's time for: {habit['name']}?")
