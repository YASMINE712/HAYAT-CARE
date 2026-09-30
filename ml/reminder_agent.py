"""Compatibility adapter for the persistent reminder scheduler."""
from worker import tick


class ReminderAgent:
    def __init__(self, store, sender=None):
        self.store, self.sender = store, sender

    def run(self):
        if self.sender:
            tick(self.store, sender=self.sender)
        else:
            tick(self.store)
