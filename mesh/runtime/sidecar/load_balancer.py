"""Load balancing algorithms for destination selection.

Provides multiple strategies for ordering destinations when multiple
agents offer the same skill:
- Round-robin: rotate through destinations in order
- Random: shuffle randomly
- Least-requests: prefer destinations with fewest active requests
- Consistent-hash: hash-based sticky routing
- Weighted: weighted random selection for traffic splitting
"""

from __future__ import annotations

import hashlib
import random
import threading
from abc import ABC, abstractmethod
from typing import Any


class LoadBalancer(ABC):
    """Abstract base for load balancing algorithms."""

    @abstractmethod
    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        """Reorder destinations by preference.

        Args:
            destinations: List of (url, agent_name) tuples.
            context: Optional context dict with keys like source_agent, skill, task_id.

        Returns:
            Reordered list of (url, agent_name) tuples.
        """


class RoundRobinBalancer(LoadBalancer):
    """Rotates through destinations using an atomic counter."""

    def __init__(self):
        self._counter = 0
        self._lock = threading.Lock()

    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        if len(destinations) <= 1:
            return destinations

        with self._lock:
            idx = self._counter % len(destinations)
            self._counter += 1

        # Rotate list so idx is first
        return destinations[idx:] + destinations[:idx]


class RandomBalancer(LoadBalancer):
    """Shuffles destinations randomly."""

    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        if len(destinations) <= 1:
            return destinations

        result = list(destinations)
        random.shuffle(result)
        return result


class LeastRequestsBalancer(LoadBalancer):
    """Prefers destinations with the fewest active requests."""

    def __init__(self):
        self._active_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, url: str) -> None:
        """Increment active request count for a destination."""
        with self._lock:
            self._active_counts[url] = self._active_counts.get(url, 0) + 1

    def decrement(self, url: str) -> None:
        """Decrement active request count for a destination."""
        with self._lock:
            count = self._active_counts.get(url, 0)
            self._active_counts[url] = max(0, count - 1)

    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        if len(destinations) <= 1:
            return destinations

        with self._lock:
            counts = {url: self._active_counts.get(url, 0) for url, _ in destinations}

        return sorted(destinations, key=lambda d: counts.get(d[0], 0))


class ConsistentHashBalancer(LoadBalancer):
    """Hash-based sticky routing using a context key."""

    def __init__(self, hash_key: str = "source_agent"):
        self._hash_key = hash_key

    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        if len(destinations) <= 1:
            return destinations

        key_value = ""
        if context:
            key_value = str(context.get(self._hash_key, ""))

        hash_int = int(hashlib.md5(key_value.encode()).hexdigest(), 16)
        idx = hash_int % len(destinations)

        # Put the hashed destination first, then the rest for failover
        return [destinations[idx]] + destinations[:idx] + destinations[idx + 1:]


class WeightedBalancer(LoadBalancer):
    """Weighted random selection for traffic splitting.

    Selects a primary destination based on cumulative weight distribution,
    then appends remaining destinations for failover.
    """

    def __init__(self, weights: dict[str, int]):
        self._weights = weights

    def select(
        self,
        destinations: list[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, str]]:
        if len(destinations) <= 1:
            return destinations

        # Build cumulative weights
        weighted = []
        for url, name in destinations:
            w = self._weights.get(name, 0)
            if w > 0:
                weighted.append((url, name, w))

        if not weighted:
            return destinations

        total = sum(w for _, _, w in weighted)
        if total == 0:
            return destinations

        # Weighted random selection
        r = random.random() * total
        cumulative = 0.0
        selected_idx = 0
        for i, (_, _, w) in enumerate(weighted):
            cumulative += w
            if r <= cumulative:
                selected_idx = i
                break

        # Put selected first, then rest for failover
        selected = (weighted[selected_idx][0], weighted[selected_idx][1])
        rest = [
            (url, name) for i, (url, name, _) in enumerate(weighted)
            if i != selected_idx
        ]
        return [selected] + rest


def create_load_balancer(algorithm: str, **kwargs: Any) -> LoadBalancer:
    """Factory function to create a load balancer by algorithm name."""
    if algorithm == "round-robin":
        return RoundRobinBalancer()
    elif algorithm == "random":
        return RandomBalancer()
    elif algorithm == "least-requests":
        return LeastRequestsBalancer()
    elif algorithm == "consistent-hash":
        hash_key = kwargs.get("consistent_hash_key", "source_agent")
        return ConsistentHashBalancer(hash_key=hash_key)
    else:
        raise ValueError(f"Unknown load balancing algorithm: {algorithm}")
