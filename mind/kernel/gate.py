"""Kernel gate evaluation helpers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .integrity import IntegrityReport, build_integrity_report
from .replay import episode_record_hash, replay_episode
from .store import MemoryStoreFactory, SQLiteMemoryStore


@dataclass(frozen=True)
class KernelGateResult:
    golden_episode_count: int
    round_trip_match_count: int
    round_trip_total: int
    replay_match_count: int
    replay_total: int
    core_object_type_count: int
    integrity_report: IntegrityReport

    @property
    def b1_pass(self) -> bool:
        return self.round_trip_match_count == self.round_trip_total

    @property
    def b2_pass(self) -> bool:
        return self.integrity_report.source_trace_coverage == 1.0

    @property
    def b3_pass(self) -> bool:
        return (
            not self.integrity_report.dangling_refs
            and not self.integrity_report.cycles
            and not self.integrity_report.version_chain_issues
        )

    @property
    def b4_pass(self) -> bool:
        return self.replay_match_count == self.replay_total == self.golden_episode_count

    @property
    def b5_pass(self) -> bool:
        return self.integrity_report.metadata_coverage == 1.0

    @property
    def kernel_gate_pass(self) -> bool:
        return self.b1_pass and self.b2_pass and self.b3_pass and self.b4_pass and self.b5_pass


def evaluate_kernel_gate(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> KernelGateResult:
    from mind.fixtures.golden_episode_set import (
        build_core_object_showcase,
        build_golden_episode_set,
    )

    fixtures = build_golden_episode_set()
    showcase = build_core_object_showcase()

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, store_factory: MemoryStoreFactory) -> KernelGateResult:
        with store_factory(store_path) as store:
            for episode in fixtures:
                store.insert_objects(episode.objects)
            store.insert_objects(showcase)

            round_trip_match_count = 0
            round_trip_total = 0
            for episode in fixtures:
                for obj in episode.objects:
                    round_trip_total += 1
                    if store.read_object(obj["id"], obj["version"]) == obj:
                        round_trip_match_count += 1

            replay_match_count = 0
            for episode in fixtures:
                replayed = replay_episode(store, episode.episode_id)
                if episode_record_hash(replayed) == episode.expected_event_hash:
                    replay_match_count += 1

            report = build_integrity_report(store.iter_objects())

        return KernelGateResult(
            golden_episode_count=len(fixtures),
            round_trip_match_count=round_trip_match_count,
            round_trip_total=round_trip_total,
            replay_match_count=replay_match_count,
            replay_total=len(fixtures),
            core_object_type_count=len(showcase),
            integrity_report=report,
        )

    factory = store_factory or default_store_factory

    if db_path is not None:
        return run(Path(db_path), factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "kernel_gate.sqlite3", factory)


def assert_kernel_gate(result: KernelGateResult) -> None:
    if not result.b1_pass:
        raise RuntimeError(
            "B-1 failed: round-trip mismatch "
            f"({result.round_trip_match_count}/{result.round_trip_total})"
        )
    if not result.b2_pass:
        raise RuntimeError(
            f"B-2 failed: source trace coverage {result.integrity_report.source_trace_coverage:.2f}"
        )
    if not result.b3_pass:
        raise RuntimeError(
            "B-3 failed: integrity issues "
            f"dangling={result.integrity_report.dangling_refs}, "
            f"cycles={result.integrity_report.cycles}, "
            f"versions={result.integrity_report.version_chain_issues}"
        )
    if not result.b4_pass:
        raise RuntimeError(
            "B-4 failed: replay fidelity mismatch "
            f"({result.replay_match_count}/{result.replay_total})"
        )
    if not result.b5_pass:
        raise RuntimeError(
            f"B-5 failed: metadata coverage {result.integrity_report.metadata_coverage:.2f}"
        )
