"""Deadline-aware strategy scheduling with a measured publication reserve."""
from __future__ import annotations

import time
from collections import defaultdict


class AnytimeScheduler:
    def __init__(self, deadline: int = 0, clock=time.time, stop_event=None):
        self.deadline = deadline
        self.clock = clock
        self.stop_event = stop_event
        self.samples: dict[str, list[float]] = defaultdict(list)
        self.publication_seconds = 0.0

    def remaining(self) -> float:
        return float("inf") if not self.deadline else self.deadline - self.clock()

    def reserve(self) -> float:
        # Initial reserve scales with the available window. Later it adapts to
        # measured write+validation duration (with a 3x safety factor).
        return max(self.publication_seconds * 3.0, max(3.0, self.remaining() * 0.05))

    def can_start(self, strategy: str) -> bool:
        if self.stop_event is not None and self.stop_event.is_set():
            return False
        if not self.deadline:
            return True
        samples = self.samples.get(strategy, ())
        estimate = (sum(samples) / len(samples) * 1.5) if samples else 0.0
        return self.remaining() > self.reserve() + estimate

    def record(self, strategy: str, elapsed: float) -> None:
        self.samples[strategy].append(max(0.0, elapsed))

    def record_publication(self, elapsed: float) -> None:
        self.publication_seconds = max(self.publication_seconds, elapsed)
