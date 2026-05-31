"""
EventQueue — Min-heap priority queue for the event-driven simulation.

Events are processed in chronological order (lowest timestamp first).
Ties are broken deterministically by bus_id to ensure reproducible results.

Uses Python's heapq for O(log n) push/pop operations.
"""
from __future__ import annotations
import heapq
from .event import Event


class EventQueue:
    """
    Min-heap priority queue for simulation events.
    
    Events are ordered by (timestamp, bus_id) for deterministic tie-breaking.
    This guarantees that two buses arriving at exactly the same time
    are always processed in a consistent order regardless of insertion order.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[float, str, Event]] = []
        self._counter: int = 0  # Insertion order for secondary tie-breaking

    def push(self, event: Event) -> None:
        """Push an event onto the queue. O(log n)."""
        # (timestamp, bus_id, counter) for stable sort
        heapq.heappush(self._heap, (event.timestamp, event.bus_id, self._counter, event))
        self._counter += 1

    def pop(self) -> Event:
        """Pop the earliest event. O(log n). Raises IndexError if empty."""
        _, _, _, event = heapq.heappop(self._heap)
        return event

    def peek(self) -> Event | None:
        """Peek at the next event without removing it. O(1)."""
        if self._heap:
            return self._heap[0][3]
        return None

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def __len__(self) -> int:
        return len(self._heap)
