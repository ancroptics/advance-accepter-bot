import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_calls=2, period=1.0):
        self.max_calls = max_calls
        self.period = period
        self._calls = {}  # user_id -> [timestamps]

    def is_allowed(self, user_id):
        now = time.time()
        if user_id not in self._calls:
            self._calls[user_id] = []
        self._calls[user_id] = [t for t in self._calls[user_id] if now - t < self.period]
        if len(self._calls[user_id]) >= self.max_calls:
            return False
        self._calls[user_id].append(now)
        return True

    def cleanup(self):
        now = time.time()
        to_delete = [uid for uid, times in self._calls.items() if all(now - t > self.period * 10 for t in times)]
        for uid in to_delete:
            del self._calls[uid]
