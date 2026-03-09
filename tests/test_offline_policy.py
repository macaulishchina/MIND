from __future__ import annotations

from mind.offline import assess_schema_promotion


def _reflection(
    object_id: str,
    *,
    episode_id: str,
    reflection_kind: str = "failure",
) -> dict:
    return {
        "id": object_id,
        "type": "ReflectionNote",
        "content": {"summary": f"{episode_id} reflection"},
        "source_refs": [episode_id, f"{episode_id}-raw-01"],
        "created_at": "2026-03-09T10:00:00+00:00",
        "updated_at": "2026-03-09T10:00:00+00:00",
        "version": 1,
        "status": "active",
        "priority": 0.8,
        "metadata": {
            "episode_id": episode_id,
            "reflection_kind": reflection_kind,
            "claims": ["stale-memory"],
        },
    }


def test_assess_schema_promotion_accepts_cross_episode_support() -> None:
    decision = assess_schema_promotion(
        [
            _reflection("episode-004-reflection", episode_id="episode-004"),
            _reflection("episode-008-reflection", episode_id="episode-008"),
        ]
    )

    assert decision.promote is True
    assert decision.supporting_episode_ids == ("episode-004", "episode-008")
    assert decision.evidence_refs == ("episode-004-reflection", "episode-008-reflection")
    assert 0.0 < decision.stability_score <= 0.95


def test_assess_schema_promotion_rejects_conflicting_reflections() -> None:
    decision = assess_schema_promotion(
        [
            _reflection(
                "episode-004-reflection",
                episode_id="episode-004",
                reflection_kind="failure",
            ),
            _reflection(
                "episode-008-reflection",
                episode_id="episode-008",
                reflection_kind="success",
            ),
        ]
    )

    assert decision.promote is False
    assert "conflicting" in decision.reason
