"""Bounded cooperative G1 scheduling; no worker, collector or journal changes."""
from collections import deque
from dataclasses import dataclass
import math
import threading
from ..recovery.rest_budget import RestBudget


@dataclass(frozen=True)
class Job:
    identity: str
    priority: int  # 0=core, 1=background
    api_weight: int = 0
    db_writes: int = 1

    def __post_init__(self):
        if (not isinstance(self.identity, str) or not self.identity
                or type(self.priority) is not int or self.priority not in (0, 1)
                or any(type(x) is not int or x < 0 for x in (self.api_weight, self.db_writes))):
            raise ValueError("Invalid job")


class AdaptiveScheduler:
    """Admission only: caller executes returned jobs and retains durable retries.

    Inject the *shared* REST budget for a real pipeline. The DB budget is a
    conservative per-minute write admission, not a throughput guarantee. If API
    admission fails after DB reservation, that reservation is retained until
    window rollover (safe overcount). RAM queues are not durable work storage.
    """
    def __init__(self, api_budget: RestBudget, db_budget: RestBudget, *, capacity=128,
                 core_reserve=16, max_batch=16):
        if (any(type(x) is not int for x in (capacity, core_reserve, max_batch))
                or not 1 <= core_reserve < capacity <= 10000 or not 1 <= max_batch <= capacity):
            raise ValueError("Invalid scheduler bounds")
        self.api, self.db = api_budget, db_budget
        self.capacity, self.reserve, self.maximum = capacity, core_reserve, max_batch
        self.batch = max_batch
        self.queues = (deque(), deque())
        self.identities = set()
        self.lock = threading.Lock()
        self.metrics = dict(admitted=0, rejected=0, duplicate=0, quota_denied=0,
                            api_weight_reserved=0, db_writes_reserved=0, peak_backlog=0)

    def submit(self, job):
        if not isinstance(job, Job):
            raise ValueError("Job required")
        with self.lock:
            if job.identity in self.identities:
                self.metrics["duplicate"] += 1
                return False
            ceiling = self.capacity if job.priority == 0 else self.capacity - self.reserve
            if len(self.identities) >= ceiling:
                self.metrics["rejected"] += 1
                return False
            self.queues[job.priority].append(job)
            self.identities.add(job.identity)
            self.metrics["peak_backlog"] = max(len(self.identities), self.metrics["peak_backlog"])
            return True

    def take(self, *, pressure):
        if isinstance(pressure, bool) or not isinstance(pressure, (int, float)) or not math.isfinite(pressure) or not 0 <= pressure <= 1:
            raise ValueError("Invalid pressure observation")
        with self.lock:
            if pressure >= .8:
                self.batch = max(1, self.batch // 2)
            elif pressure <= .3:
                self.batch = min(self.maximum, self.batch + 1)
            result = []
            for _ in range(self.batch):
                queue = self.queues[0] or self.queues[1]
                if not queue:
                    break
                job = queue[0]
                # P0 continues under pressure; background yields completely.
                if job.priority and pressure >= .8:
                    break
                try:
                    self.db.acquire(job.db_writes, core=job.priority == 0)
                    self.metrics["db_writes_reserved"] += job.db_writes
                    self.api.acquire(job.api_weight, core=job.priority == 0)
                    self.metrics["api_weight_reserved"] += job.api_weight
                except RuntimeError:
                    self.metrics["quota_denied"] += 1
                    break
                queue.popleft()
                self.identities.remove(job.identity)
                self.metrics["admitted"] += 1
                result.append(job)
            return result
