"""Process-shared conservative REST admission; no waiting in critical callbacks."""
from __future__ import annotations
import threading
import time


class RestBudget:
    def __init__(self, limit=1200, reserve=100, clock=time.monotonic):
        self.limit, self.reserve, self.clock = limit, reserve, clock
        self.lock = threading.Lock()
        self.started = clock()
        self.used = 0
        self.blocked_until = 0.0

    def acquire(self, cost=2, *, core=False):
        with self.lock:
            now = self.clock()
            if now - self.started >= 60:
                self.started, self.used = now, 0
            ceiling = self.limit if core else self.limit - self.reserve
            if now < self.blocked_until or self.used + cost > ceiling:
                raise RuntimeError("REST budget/cooldown admission denied")
            self.used += cost

    def observe(self, used):
        with self.lock:
            self.used = max(self.used, used)

    def cooldown(self, seconds):
        with self.lock:
            self.blocked_until = max(self.blocked_until,
                                     self.clock() + min(max(seconds, 1), 86400))


SHARED_REST_BUDGET = RestBudget()
