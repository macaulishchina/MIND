"""Graph-augmented retrieval helpers (Phase γ-2).

Provides BFS-based expansion over the LinkEdge adjacency graph so that the
access service can surface related objects that keyword/vector retrieval might
miss.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Protocol


class _GraphStore(Protocol):
    def iter_latest_objects(
        self,
        *,
        statuses: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]: ...

    def is_object_concealed(self, object_id: str) -> bool: ...


def build_adjacency_index(store: _GraphStore) -> dict[str, list[str]]:
    """Build a bidirectional adjacency index from all active LinkEdge objects.

    Only active, non-concealed LinkEdges are included.  The index is
    bidirectional: both the source and destination are recorded as neighbours
    of each other.

    Args:
        store: A :class:`MemoryStore`-compatible object that exposes
            ``iter_latest_objects`` and ``is_object_concealed``.

    Returns:
        Mapping from object ID to list of adjacent object IDs.
    """
    adjacency: dict[str, list[str]] = {}
    all_objects = store.iter_latest_objects(statuses=("active",))
    for obj in all_objects:
        if obj.get("type") != "LinkEdge":
            continue
        if store.is_object_concealed(obj["id"]):
            continue
        content = obj.get("content", {})
        if not isinstance(content, dict):
            continue
        src = content.get("src_id")
        dst = content.get("dst_id")
        if not src or not dst or not isinstance(src, str) or not isinstance(dst, str):
            continue
        adjacency.setdefault(src, []).append(dst)
        adjacency.setdefault(dst, []).append(src)
    return adjacency


def expand_by_graph(
    seed_ids: list[str],
    adjacency: dict[str, list[str]],
    *,
    hops: int = 1,
    max_expand: int = 10,
) -> list[str]:
    """BFS-expand seed IDs by traversing the adjacency graph.

    Returns the IDs discovered beyond the seed set, up to *max_expand* new
    unique IDs.  Cycle-safe: each node is visited at most once.

    Args:
        seed_ids: Starting object IDs.
        adjacency: Bidirectional adjacency index from
            :func:`build_adjacency_index`.
        hops: Number of graph hops to traverse (1 = direct neighbours, 2 =
            neighbours-of-neighbours, …).
        max_expand: Maximum number of *new* IDs to return.

    Returns:
        List of newly discovered object IDs (not including seeds themselves).
    """
    if hops < 1 or not seed_ids:
        return []

    visited: set[str] = set(seed_ids)
    queue: deque[tuple[str, int]] = deque((sid, 0) for sid in seed_ids)
    discovered: list[str] = []

    while queue and len(discovered) < max_expand:
        current_id, depth = queue.popleft()
        if depth >= hops:
            continue
        for neighbour in adjacency.get(current_id, []):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            discovered.append(neighbour)
            if len(discovered) >= max_expand:
                break
            queue.append((neighbour, depth + 1))

    return discovered
