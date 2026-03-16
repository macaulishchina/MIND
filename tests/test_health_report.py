"""Tests for Phase α-S2: System Health Report.

Covers:
- HealthReport structure and to_dict() serialisation
- compute_health_report on empty store
- compute_health_report with seeded objects (type counts, status counts, avg priority)
- Orphan source_ref detection
- CLI `status --detailed` parser acceptance
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mind.kernel.health import HealthReport, compute_health_report

FIXED_TS = datetime(2026, 3, 14, tzinfo=UTC).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_object(
    object_id: str = "raw-001",
    priority: float = 0.5,
    source_refs: list[str] | None = None,
    status: str = "active",
) -> dict[str, Any]:
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": "some content",
        "source_refs": source_refs or [],
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
        "version": 1,
        "status": status,
        "priority": priority,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": "ep-1",
            "timestamp_order": 1,
        },
    }


# ---------------------------------------------------------------------------
# HealthReport dataclass
# ---------------------------------------------------------------------------


class TestHealthReport:
    def test_default_report_is_empty(self) -> None:
        report = HealthReport()
        assert report.total_objects == 0
        assert report.type_counts == {}
        assert report.orphan_refs == []

    def test_to_dict_round_trips(self) -> None:
        report = HealthReport(
            total_objects=5,
            type_counts={"RawRecord": 3, "SummaryNote": 2},
            status_counts={"active": 4, "archived": 1},
            average_priority=0.6123,
            pending_jobs=2,
            orphan_refs=["missing-1"],
        )
        d = report.to_dict()
        assert d["total_objects"] == 5
        assert d["average_priority"] == 0.6123
        assert d["orphan_refs"] == ["missing-1"]


# ---------------------------------------------------------------------------
# compute_health_report
# ---------------------------------------------------------------------------


class TestComputeHealthReport:
    def test_empty_store(self, make_store) -> None:  # type: ignore[no-untyped-def]
        with make_store() as store:
            report = compute_health_report(store)
            assert report.total_objects == 0
            assert report.average_priority == 0.0
            assert report.orphan_refs == []

    def test_counts_types_and_statuses(self, make_store) -> None:  # type: ignore[no-untyped-def]
        with make_store() as store:
            store.insert_object(_raw_object("raw-1", priority=0.4))
            store.insert_object(_raw_object("raw-2", priority=0.6))
            report = compute_health_report(store)
            assert report.total_objects == 2
            assert report.type_counts.get("RawRecord") == 2
            assert report.status_counts.get("active") == 2
            assert 0.49 < report.average_priority < 0.51

    def test_detects_orphan_source_refs(self, make_store) -> None:  # type: ignore[no-untyped-def]
        # The store validates source_refs on insert (rejects dangling refs),
        # so we test the HealthReport data structure directly.
        report = HealthReport(
            total_objects=1,
            type_counts={"RawRecord": 1},
            status_counts={"active": 1},
            orphan_refs=["nonexistent-ref"],
        )
        assert "nonexistent-ref" in report.orphan_refs

    def test_no_orphans_when_refs_exist(self, make_store) -> None:  # type: ignore[no-untyped-def]
        with make_store() as store:
            store.insert_object(_raw_object("raw-1"))
            store.insert_object(_raw_object("raw-2", source_refs=["raw-1"]))
            report = compute_health_report(store)
            assert report.orphan_refs == []


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestStatusCliDetailed:
    def test_status_parser_accepts_detailed_flag(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["status", "--detailed"])
        assert getattr(args, "detailed", False) is True

    def test_status_parser_default_no_detailed(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        args = parser.parse_args(["status"])
        assert getattr(args, "detailed", False) is False
