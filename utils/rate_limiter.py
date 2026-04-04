import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_calls=5, period=60):
        self.max_calls = max_calls
        self.period = period
        self._calls = defaultdict(list)

    def is_allowed(self, key):
        now = time.time()
        calls = self._calls[key]
        calls[:] = [t for t in calls if now - t < self.period]
        if len(calls) >= self.max_calls:
            return False
        calls.append(now)
        return True
