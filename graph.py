"""
tf2_visualizer.graph — Thread-safe TF tree data model.

Maintains the directed acyclic graph of TF frames. Every edge represents
a transform from parent → child.  The model is designed for concurrent
producer (ROS subscriber thread) / consumer (GUI thread) access.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Set, Tuple


@dataclass(frozen=True)
class FrameEdge:
    """Immutable snapshot of a single TF edge."""

    parent: str
    child: str
    last_seen: float  # monotonic timestamp
    is_static: bool
    translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


class TFGraph:
    """
    Thread-safe, observable TF frame graph.

    Internally stores edges keyed by (parent, child).  A monotonically
    increasing *revision* counter is bumped on every structural change
    (new edge or removed edge) so that the GUI can cheaply poll whether
    a repaint is needed.
    """

    def __init__(self, stale_timeout: float = 10.0) -> None:
        self._lock = threading.Lock()
        self._edges: Dict[Tuple[str, str], FrameEdge] = {}
        self._revision: int = 0
        self._stale_timeout = stale_timeout  # seconds before a dynamic edge is pruned

    # ── producer API (called from ROS callback thread) ──────────────

    def update_edge(
        self,
        parent: str,
        child: str,
        is_static: bool,
        translation: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    ) -> None:
        key = (parent, child)
        now = time.monotonic()
        new_edge = FrameEdge(
            parent=parent,
            child=child,
            last_seen=now,
            is_static=is_static,
            translation=translation,
            rotation=rotation,
        )
        with self._lock:
            old = self._edges.get(key)
            self._edges[key] = new_edge
            if old is None:  # structural change
                self._revision += 1

    def prune_stale(self) -> int:
        """Remove dynamic edges older than *stale_timeout*.  Returns count removed."""
        cutoff = time.monotonic() - self._stale_timeout
        removed = 0
        with self._lock:
            stale_keys = [k for k, e in self._edges.items() if not e.is_static and e.last_seen < cutoff]
            for k in stale_keys:
                del self._edges[k]
                removed += 1
            if removed:
                self._revision += 1
        return removed

    # ── consumer API (called from GUI thread) ───────────────────────

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def snapshot(self) -> Tuple[int, Dict[Tuple[str, str], FrameEdge]]:
        """Return (revision, shallow copy of edges dict)."""
        with self._lock:
            return self._revision, dict(self._edges)

    def roots(self) -> Set[str]:
        """Return frames that are parents but never children."""
        with self._lock:
            parents = {e.parent for e in self._edges.values()}
            children = {e.child for e in self._edges.values()}
            return parents - children

    def children_of(self, parent: str) -> list[FrameEdge]:
        with self._lock:
            return [e for e in self._edges.values() if e.parent == parent]
