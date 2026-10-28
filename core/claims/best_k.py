"""Unique semantic Top-K selection with deterministic dependency penalties."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .ranker import RankedClaim


class BestKPool:
    def __init__(self, limit: int = 1000):
        self.limit = limit
        self._items: dict[tuple, RankedClaim] = {}

    def add(self, candidate: RankedClaim) -> bool:
        previous = self._items.get(candidate.semantic_key)
        if previous is not None and self._order(previous) <= self._order(candidate):
            return False
        self._items[candidate.semantic_key] = candidate
        return True

    @staticmethod
    def _order(item: RankedClaim) -> tuple:
        return (-item.score, item.claim["type"], item.claim["id"])

    def selected(self, limit: int | None = None) -> list[RankedClaim]:
        # Greedy portfolio penalty discourages a large pool resting on the same rows.
        remaining = sorted(self._items.values(), key=self._order)
        chosen: list[RankedClaim] = []
        usage: Counter[str] = Counter()
        target = self.limit if limit is None else min(self.limit, max(0, limit))
        while remaining and len(chosen) < target:
            best = min(remaining, key=lambda c: (
                -(c.score - 0.035 * sum(usage[row] for row in c.evidence_ids)),
                c.claim["type"], c.claim["id"],
            ))
            chosen.append(best)
            usage.update(best.evidence_ids)
            remaining.remove(best)
        return chosen

    def __len__(self) -> int:
        return len(self._items)

