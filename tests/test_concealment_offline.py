from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.governance import ConcealmentRecord
from mind.kernel.replay import replay_episode
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    ReflectEpisodeJobPayload,
    new_offline_job,
    select_replay_targets,
)

FIXED_TIMESTAMP = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)


def test_offline_reflection_replay_excludes_concealed_raw_records(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_conceal_offline.sqlite3"
    episode = build_golden_episode_set()[1]
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    concealed_raw_id = raw_records[-1]["id"]
    visible_raw_ids = [record["id"] for record in raw_records[:-1]]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episode.objects)
        store.record_concealment(
            ConcealmentRecord(
                concealment_id="conceal-offline-001",
                operation_id="op-offline-conceal-001",
                object_id=concealed_raw_id,
                actor="governance-operator",
                concealed_at=FIXED_TIMESTAMP,
                reason="exclude hidden raw record from replay",
            )
        )

        replayed = replay_episode(store, episode.episode_id)
        maintenance = OfflineMaintenanceService(store, clock=lambda: FIXED_TIMESTAMP)
        result = maintenance.process_job(
            new_offline_job(
                job_id="offline-reflect-hidden-raw",
                job_kind=OfflineJobKind.REFLECT_EPISODE,
                payload=ReflectEpisodeJobPayload(
                    episode_id=episode.episode_id,
                    focus="offline conceal replay regression",
                ),
                now=FIXED_TIMESTAMP,
            ),
            actor="phase-h-offline-worker",
        )

    assert [record["id"] for record in replayed] == visible_raw_ids
    assert concealed_raw_id not in result["source_refs"]
    assert result["source_refs"] == [episode.episode_id, *visible_raw_ids[-2:]]


def test_select_replay_targets_skips_concealed_objects(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_conceal_replay_targets.sqlite3"
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.record_concealment(
            ConcealmentRecord(
                concealment_id="conceal-offline-002",
                operation_id="op-offline-conceal-002",
                object_id="showcase-reflection",
                actor="governance-operator",
                concealed_at=FIXED_TIMESTAMP,
                reason="exclude hidden object from replay target ranking",
            )
        )

        targets = select_replay_targets(
            store,
            ("showcase-reflection", "showcase-summary"),
            top_k=2,
        )

    assert [target.object_id for target in targets] == ["showcase-summary"]
