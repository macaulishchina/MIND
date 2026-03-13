"""Tests for Phase γ-2: Graph-augmented retrieval."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mind.kernel.graph import build_adjacency_index, expand_by_graph
from mind.kernel.store import SQLiteMemoryStore
from mind.offline_jobs import DiscoverLinksJobPayload, OfflineJobKind


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _raw_object(obj_id: str, episode_id: str = "ep-1") -> dict:
    return {
        "id": obj_id,
        "type": "RawRecord",
        "content": f"content for {obj_id}",
        "source_refs": [],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": episode_id,
            "timestamp_order": 1,
        },
    }


def _link_object(src_id: str, dst_id: str, link_id: str | None = None) -> dict:
    lid = link_id or f"link-{src_id}-{dst_id}"
    return {
        "id": lid,
        "type": "LinkEdge",
        "content": {
            "src_id": src_id,
            "dst_id": dst_id,
            "relation_type": "related",
        },
        "source_refs": [src_id, dst_id],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "confidence": 0.8,
            "evidence_refs": [src_id, dst_id],
        },
    }


# ─── build_adjacency_index ───────────────────────────────────────────────────


class TestBuildAdjacencyIndex:
    def _store_with_links(self) -> SQLiteMemoryStore:
        store = SQLiteMemoryStore(":memory:")
        for i in range(1, 5):
            store.insert_object(_raw_object(f"obj-{i}"))
        store.insert_object(_link_object("obj-1", "obj-2"))
        store.insert_object(_link_object("obj-2", "obj-3"))
        return store

    def test_bidirectional_edges(self) -> None:
        store = self._store_with_links()
        adj = build_adjacency_index(store)
        # obj-1 → obj-2 (bidirectional)
        assert "obj-2" in adj.get("obj-1", [])
        assert "obj-1" in adj.get("obj-2", [])

    def test_no_links_returns_empty(self) -> None:
        store = SQLiteMemoryStore(":memory:")
        store.insert_object(_raw_object("obj-solo"))
        adj = build_adjacency_index(store)
        assert adj == {}

    def test_only_active_links_included(self) -> None:
        store = SQLiteMemoryStore(":memory:")
        store.insert_object(_raw_object("obj-a"))
        store.insert_object(_raw_object("obj-b"))
        link = _link_object("obj-a", "obj-b", "link-ab")
        link["status"] = "deprecated"
        store.insert_object(link)
        adj = build_adjacency_index(store)
        # deprecated link should be excluded
        assert "obj-b" not in adj.get("obj-a", [])

    def test_transitive_chain(self) -> None:
        store = SQLiteMemoryStore(":memory:")
        for i in range(1, 5):
            store.insert_object(_raw_object(f"obj-{i}"))
        store.insert_object(_link_object("obj-1", "obj-2"))
        store.insert_object(_link_object("obj-2", "obj-3"))
        store.insert_object(_link_object("obj-3", "obj-4"))
        adj = build_adjacency_index(store)
        assert "obj-2" in adj["obj-1"]
        assert "obj-3" in adj["obj-2"]
        assert "obj-4" in adj["obj-3"]


# ─── expand_by_graph ─────────────────────────────────────────────────────────


class TestExpandByGraph:
    def _simple_adj(self) -> dict[str, list[str]]:
        # obj-1 – obj-2 – obj-3 – obj-4
        return {
            "obj-1": ["obj-2"],
            "obj-2": ["obj-1", "obj-3"],
            "obj-3": ["obj-2", "obj-4"],
            "obj-4": ["obj-3"],
        }

    def test_one_hop_direct_neighbours(self) -> None:
        adj = self._simple_adj()
        expanded = expand_by_graph(["obj-1"], adj, hops=1)
        assert "obj-2" in expanded
        assert "obj-3" not in expanded
        assert "obj-1" not in expanded

    def test_two_hop_expands_further(self) -> None:
        adj = self._simple_adj()
        expanded = expand_by_graph(["obj-1"], adj, hops=2)
        assert "obj-2" in expanded
        assert "obj-3" in expanded
        assert "obj-4" not in expanded

    def test_max_expand_limits_results(self) -> None:
        adj: dict[str, list[str]] = {f"obj-{i}": [f"obj-{i + 1}"] for i in range(20)}
        expanded = expand_by_graph(["obj-0"], adj, hops=10, max_expand=3)
        assert len(expanded) <= 3

    def test_cycle_safety(self) -> None:
        # Circular adjacency: A → B → C → A
        adj = {
            "A": ["B"],
            "B": ["A", "C"],
            "C": ["B", "A"],
        }
        expanded = expand_by_graph(["A"], adj, hops=5, max_expand=10)
        # Should not loop forever; should contain B and C but not A.
        assert "A" not in expanded
        assert "B" in expanded
        assert "C" in expanded

    def test_zero_hops_returns_empty(self) -> None:
        adj = self._simple_adj()
        assert expand_by_graph(["obj-1"], adj, hops=0) == []

    def test_empty_seeds_returns_empty(self) -> None:
        adj = self._simple_adj()
        assert expand_by_graph([], adj, hops=1) == []

    def test_isolated_seed_returns_empty(self) -> None:
        adj = self._simple_adj()
        expanded = expand_by_graph(["isolated"], adj, hops=1)
        assert expanded == []

    def test_seed_not_included_in_result(self) -> None:
        adj = self._simple_adj()
        expanded = expand_by_graph(["obj-2"], adj, hops=1)
        assert "obj-2" not in expanded

    def test_multiple_seeds(self) -> None:
        adj = self._simple_adj()
        # Seeds obj-1 and obj-4; should pick up obj-2 and obj-3.
        expanded = expand_by_graph(["obj-1", "obj-4"], adj, hops=1)
        assert "obj-2" in expanded
        assert "obj-3" in expanded


# ─── build_adjacency_index with concealed links ──────────────────────────────


class TestAdjacencyIndexConcealment:
    def test_concealed_link_excluded(self) -> None:
        store = SQLiteMemoryStore(":memory:")
        store.insert_object(_raw_object("obj-x"))
        store.insert_object(_raw_object("obj-y"))
        link = _link_object("obj-x", "obj-y", "link-xy")
        store.insert_object(link)
        # Conceal the link
        from mind.kernel.governance import ConcealmentRecord
        from datetime import UTC, datetime as _datetime
        store.record_concealment(
            ConcealmentRecord(
                concealment_id="c-xy",
                operation_id="op-conceal-test",
                object_id="link-xy",
                actor="test-actor",
                reason="test concealment",
                concealed_at=_datetime.now(UTC),
            )
        )
        adj = build_adjacency_index(store)
        assert "obj-y" not in adj.get("obj-x", [])


# ─── DISCOVER_LINKS job kind ─────────────────────────────────────────────────


class TestDiscoverLinksJobKind:
    def test_discover_links_kind_exists(self) -> None:
        assert OfflineJobKind.DISCOVER_LINKS == "discover_links"

    def test_discover_links_payload(self) -> None:
        payload = DiscoverLinksJobPayload(
            object_ids=["obj-1", "obj-2"],
            top_k=3,
            min_similarity=0.75,
        )
        assert payload.top_k == 3
        assert payload.min_similarity == 0.75

    def test_discover_links_payload_defaults(self) -> None:
        payload = DiscoverLinksJobPayload()
        assert payload.top_k >= 1
        assert 0.0 <= payload.min_similarity <= 1.0


# ─── Integration: access service graph expand ────────────────────────────────


class TestAccessServiceGraphExpand:
    """Verify that graph expansion is wired into the access service."""

    def _populated_store(self) -> SQLiteMemoryStore:
        store = SQLiteMemoryStore(":memory:")
        for i in range(1, 5):
            store.insert_object(_raw_object(f"graph-obj-{i}", episode_id=f"ep-{i}"))
        # Link obj-1 → obj-2 so graph expansion should add obj-2 when seeding obj-1.
        store.insert_object(_link_object("graph-obj-1", "graph-obj-2"))
        return store

    def test_graph_hops_for_mode(self) -> None:
        from mind.access.service import _graph_hops_for_mode
        from mind.access.contracts import AccessMode

        assert _graph_hops_for_mode(AccessMode.FLASH) == 0
        assert _graph_hops_for_mode(AccessMode.RECALL) == 1
        assert _graph_hops_for_mode(AccessMode.RECONSTRUCT) == 2
        assert _graph_hops_for_mode(AccessMode.REFLECTIVE_ACCESS) == 2
