"""Replay helpers for GoldenEpisodeSet validation."""

from __future__ import annotations

import hashlib
import json

from .store import MemoryStore


def replay_episode(store: MemoryStore, episode_id: str) -> list[dict]:
    """Return replayable raw records for an episode in timestamp order."""

    return store.raw_records_for_episode(episode_id)


def episode_record_hash(records: list[dict]) -> str:
    """Create a stable hash for event-order fidelity checks."""

    canonical = []
    for record in records:
        canonical.append(
            {
                "id": record["id"],
                "record_kind": record["metadata"]["record_kind"],
                "timestamp_order": record["metadata"]["timestamp_order"],
                "content": record["content"],
            }
        )
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
