from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.integrity import build_integrity_report
from mind.kernel.phase_b import assert_phase_b_gate, evaluate_phase_b_gate
from mind.kernel.replay import episode_record_hash, replay_episode
from mind.kernel.schema import SchemaValidationError
from mind.kernel.store import MemoryStoreFactory, SQLiteMemoryStore, StoreError


class PhaseBGateTests(unittest.TestCase):
    def test_phase_b_gate_metrics(self) -> None:
        result = evaluate_phase_b_gate()

        self.assertEqual(result.golden_episode_count, 20)
        self.assertEqual(result.core_object_type_count, 8)
        self.assertEqual(result.round_trip_match_count, result.round_trip_total)
        self.assertEqual(result.replay_match_count, result.replay_total)
        self.assertTrue(result.b1_pass)
        self.assertTrue(result.b2_pass)
        self.assertTrue(result.b3_pass)
        self.assertTrue(result.b4_pass)
        self.assertTrue(result.b5_pass)
        self.assertTrue(result.phase_b_pass)
        assert_phase_b_gate(result)

    def test_phase_b_gate_accepts_store_factory(self) -> None:
        def store_factory(path: Path) -> SQLiteMemoryStore:
            return SQLiteMemoryStore(path)

        typed_factory: MemoryStoreFactory = store_factory
        result = evaluate_phase_b_gate(store_factory=typed_factory)

        self.assertTrue(result.phase_b_pass)
        self.assertEqual(result.golden_episode_count, 20)

    def test_golden_episode_round_trip_and_replay(self) -> None:
        fixtures = build_golden_episode_set()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                for episode in fixtures:
                    store.insert_objects(episode.objects)

                for episode in fixtures:
                    replayed_records = replay_episode(store, episode.episode_id)
                    self.assertEqual(
                        episode.expected_event_hash,
                        episode_record_hash(replayed_records),
                        msg=f"event-order hash mismatch for {episode.episode_id}",
                    )

                    for obj in episode.objects:
                        self.assertEqual(store.read_object(obj["id"], obj["version"]), obj)

                report = build_integrity_report(store.iter_objects())

        self.assertEqual(report.source_trace_coverage, 1.0)
        self.assertEqual(report.metadata_coverage, 1.0)
        self.assertEqual(report.dangling_refs, [])
        self.assertEqual(report.cycles, [])
        self.assertEqual(report.version_chain_issues, [])

    def test_store_accepts_all_core_object_types(self) -> None:
        showcase = build_core_object_showcase()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "showcase.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                store.insert_objects(showcase)
                stored = store.iter_objects()

        self.assertEqual(len(stored), 8)
        report = build_integrity_report(stored)
        self.assertEqual(report.source_trace_coverage, 1.0)
        self.assertEqual(report.metadata_coverage, 1.0)
        self.assertEqual(report.dangling_refs, [])
        self.assertEqual(report.cycles, [])
        self.assertEqual(report.version_chain_issues, [])

    def test_store_rejects_dangling_source_refs(self) -> None:
        showcase = build_core_object_showcase()
        broken = dict(showcase[1])
        broken["id"] = "broken-episode"
        broken["source_refs"] = ["missing-raw-record"]
        broken["metadata"] = dict(broken["metadata"])
        broken["metadata"]["record_refs"] = ["missing-raw-record"]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "broken.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                store.insert_object(showcase[0])
                with self.assertRaises(StoreError):
                    store.insert_object(broken)

    def test_store_rejects_non_contiguous_versions(self) -> None:
        showcase = build_core_object_showcase()
        summary_v2 = dict(showcase[2])
        summary_v2["version"] = 2
        summary_v2["updated_at"] = "2026-01-01T00:02:00+00:00"
        summary_v2["metadata"] = dict(summary_v2["metadata"])

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "version-gap.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                store.insert_object(showcase[0])
                with self.assertRaises(StoreError):
                    store.insert_object(summary_v2)

    def test_store_rejects_reserved_control_plane_metadata(self) -> None:
        showcase = build_core_object_showcase()
        polluted = dict(showcase[2])
        polluted["metadata"] = dict(polluted["metadata"])
        polluted["metadata"]["governance_projection"] = {"claims": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "reserved-metadata.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                store.insert_object(showcase[0])
                with self.assertRaises(SchemaValidationError):
                    store.insert_object(polluted)

    # ------------------------------------------------------------------
    # Regression tests for audit findings I-1 and I-2
    # ------------------------------------------------------------------

    def test_insert_objects_is_atomic(self) -> None:
        """I-1: insert_objects must be all-or-nothing.

        If the Nth object in a batch fails, none of the first N-1 objects
        should remain in the store.
        """
        showcase = build_core_object_showcase()
        raw = showcase[0]  # valid RawRecord (depends on nothing)

        # Build 3 valid objects + 1 invalid (dangling source_ref)
        good_1 = dict(raw, id="atomic-1")
        good_2 = dict(raw, id="atomic-2")
        good_3 = dict(raw, id="atomic-3")
        bad_4 = dict(raw, id="atomic-4", source_refs=["nonexistent-ref"])

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "atomic.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                with self.assertRaises(StoreError):
                    store.insert_objects([good_1, good_2, good_3, bad_4])

                # None of the 3 good objects should be persisted
                self.assertFalse(store.has_object("atomic-1"))
                self.assertFalse(store.has_object("atomic-2"))
                self.assertFalse(store.has_object("atomic-3"))
                self.assertFalse(store.has_object("atomic-4"))

    def test_store_rejects_type_change_across_versions(self) -> None:
        """I-2: an object's type must remain stable across versions.

        Writing version 2 with a different type than version 1 must raise.
        """
        showcase = build_core_object_showcase()
        raw = showcase[0]  # RawRecord, used only as dependency

        # SummaryNote v1
        summary_v1 = {
            "id": "type-change-test",
            "type": "SummaryNote",
            "version": 1,
            "source_refs": [raw["id"]],
            "content": {"summary": "original"},
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": [raw["id"]],
                "compression_ratio_estimate": 0.5,
            },
        }
        # ReflectionNote v2 — same id, different type
        reflection_v2 = {
            "id": "type-change-test",
            "type": "ReflectionNote",
            "version": 2,
            "source_refs": [raw["id"]],
            "content": {"insight": "changed type"},
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:01:00+00:00",
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "episode_id": "ep-1",
                "reflection_kind": "success",
                "claims": ["some claim"],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "type-change.sqlite3"
            with SQLiteMemoryStore(db_path) as store:
                store.insert_object(raw)
                store.insert_object(summary_v1)
                with self.assertRaises(StoreError):
                    store.insert_object(reflection_v2)


if __name__ == "__main__":
    unittest.main()
