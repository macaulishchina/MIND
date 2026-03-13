"""Tests for Phase γ-1: PolicyNote / PreferenceNote new object types."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mind.kernel.schema import (
    CORE_OBJECT_TYPES,
    REQUIRED_METADATA_FIELDS,
    SchemaValidationError,
    ensure_valid_object,
    validate_object,
)
from mind.kernel.store import SQLiteMemoryStore
from mind.offline.promotion import (
    POLICY_PROMOTION_MIN_EPISODES,
    PREFERENCE_PROMOTION_MIN_EPISODES,
    assess_policy_promotion,
    assess_preference_promotion,
    assess_schema_promotion,
)
from mind.offline_jobs import (
    OfflineJobKind,
    PromotePolicyJobPayload,
    PromotePreferenceJobPayload,
)


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _base_object(obj_type: str, obj_id: str = "obj-1") -> dict:
    return {
        "id": obj_id,
        "type": obj_type,
        "content": "test content",
        "source_refs": ["src-1"],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {},
    }


# ─── Schema definitions ─────────────────────────────────────────────────────


class TestNewTypesInSchema:
    def test_policy_note_in_core_types(self) -> None:
        assert "PolicyNote" in CORE_OBJECT_TYPES

    def test_preference_note_in_core_types(self) -> None:
        assert "PreferenceNote" in CORE_OBJECT_TYPES

    def test_artifact_index_in_core_types(self) -> None:
        assert "ArtifactIndex" in CORE_OBJECT_TYPES

    def test_policy_note_required_metadata(self) -> None:
        fields = REQUIRED_METADATA_FIELDS["PolicyNote"]
        assert "trigger_condition" in fields
        assert "action_pattern" in fields
        assert "evidence_refs" in fields
        assert "confidence" in fields
        assert "applies_to_scope" in fields

    def test_preference_note_required_metadata(self) -> None:
        fields = REQUIRED_METADATA_FIELDS["PreferenceNote"]
        assert "preference_key" in fields
        assert "preference_value" in fields
        assert "strength" in fields
        assert "evidence_refs" in fields


# ─── PolicyNote schema validation ────────────────────────────────────────────


class TestPolicyNoteValidation:
    def _policy_note(self, obj_id: str = "policy-1") -> dict:
        obj = _base_object("PolicyNote", obj_id)
        obj["metadata"] = {
            "trigger_condition": "user asks for decision help",
            "action_pattern": "recommend top-3 options",
            "evidence_refs": ["ep-1", "ep-2"],
            "confidence": 0.8,
            "applies_to_scope": "decision_tasks",
        }
        return obj

    def test_valid_policy_note(self) -> None:
        errors = validate_object(self._policy_note())
        assert errors == []

    def test_missing_trigger_condition(self) -> None:
        obj = self._policy_note()
        del obj["metadata"]["trigger_condition"]
        errors = validate_object(obj)
        assert any("trigger_condition" in e for e in errors)

    def test_invalid_confidence_range(self) -> None:
        obj = self._policy_note()
        obj["metadata"]["confidence"] = 1.5
        errors = validate_object(obj)
        assert any("confidence" in e for e in errors)

    def test_confidence_at_boundary(self) -> None:
        obj = self._policy_note()
        obj["metadata"]["confidence"] = 1.0
        assert validate_object(obj) == []

    def test_evidence_refs_must_be_list(self) -> None:
        obj = self._policy_note()
        obj["metadata"]["evidence_refs"] = "not-a-list"
        errors = validate_object(obj)
        assert any("evidence_refs" in e for e in errors)

    def test_ensure_valid_raises(self) -> None:
        obj = self._policy_note()
        del obj["metadata"]["action_pattern"]
        with pytest.raises(SchemaValidationError):
            ensure_valid_object(obj)


# ─── PreferenceNote schema validation ────────────────────────────────────────


class TestPreferenceNoteValidation:
    def _preference_note(self, obj_id: str = "pref-1") -> dict:
        obj = _base_object("PreferenceNote", obj_id)
        obj["metadata"] = {
            "preference_key": "output_format",
            "preference_value": "bullet_points",
            "strength": 0.9,
            "evidence_refs": ["ep-1", "ep-2"],
        }
        return obj

    def test_valid_preference_note(self) -> None:
        assert validate_object(self._preference_note()) == []

    def test_missing_preference_key(self) -> None:
        obj = self._preference_note()
        del obj["metadata"]["preference_key"]
        errors = validate_object(obj)
        assert any("preference_key" in e for e in errors)

    def test_strength_out_of_range(self) -> None:
        obj = self._preference_note()
        obj["metadata"]["strength"] = -1.5
        errors = validate_object(obj)
        assert any("strength" in e for e in errors)

    def test_negative_strength_allowed(self) -> None:
        obj = self._preference_note()
        obj["metadata"]["strength"] = -0.5
        assert validate_object(obj) == []

    def test_evidence_refs_must_be_list(self) -> None:
        obj = self._preference_note()
        obj["metadata"]["evidence_refs"] = "not-a-list"
        errors = validate_object(obj)
        assert any("evidence_refs" in e for e in errors)


# ─── CRUD round-trip via SQLiteMemoryStore ───────────────────────────────────


class TestNewTypesCRUD:
    def _store(self) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(":memory:")

    def _seed_source(self, store: SQLiteMemoryStore, src_id: str) -> None:
        """Insert a RawRecord to satisfy source_refs constraint."""
        store.insert_object({
            "id": src_id,
            "type": "RawRecord",
            "content": "seed",
            "source_refs": [],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "record_kind": "user_message",
                "episode_id": "ep-seed",
                "timestamp_order": 1,
            },
        })

    def test_policy_note_write_read(self) -> None:
        store = self._store()
        self._seed_source(store, "ep-1")
        obj = {
            "id": "policy-crud-1",
            "type": "PolicyNote",
            "content": "always summarise in bullet points",
            "source_refs": ["ep-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.7,
            "metadata": {
                "trigger_condition": "any summarise request",
                "action_pattern": "use bullet list format",
                "evidence_refs": ["ep-1"],
                "confidence": 0.75,
                "applies_to_scope": "all",
            },
        }
        ensure_valid_object(obj)
        store.insert_object(obj)
        read = store.read_object("policy-crud-1")
        assert read["type"] == "PolicyNote"
        assert read["metadata"]["trigger_condition"] == "any summarise request"

    def test_preference_note_write_read(self) -> None:
        store = self._store()
        self._seed_source(store, "ep-2")
        obj = {
            "id": "pref-crud-1",
            "type": "PreferenceNote",
            "content": "user prefers concise answers",
            "source_refs": ["ep-2"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.6,
            "metadata": {
                "preference_key": "answer_length",
                "preference_value": "concise",
                "strength": 0.8,
                "evidence_refs": ["ep-2"],
            },
        }
        ensure_valid_object(obj)
        store.insert_object(obj)
        read = store.read_object("pref-crud-1")
        assert read["type"] == "PreferenceNote"
        assert read["metadata"]["preference_value"] == "concise"

    def test_policy_note_retrieved_in_iter(self) -> None:
        store = self._store()
        self._seed_source(store, "ep-3")
        obj = {
            "id": "policy-iter-1",
            "type": "PolicyNote",
            "content": "policy content",
            "source_refs": ["ep-3"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "trigger_condition": "any",
                "action_pattern": "act",
                "evidence_refs": ["ep-3"],
                "confidence": 0.5,
                "applies_to_scope": "general",
            },
        }
        store.insert_object(obj)
        all_objs = store.iter_latest_objects()
        ids = [o["id"] for o in all_objs]
        assert "policy-iter-1" in ids


# ─── Promotion strategies ────────────────────────────────────────────────────


class TestPolicyPromotion:
    def _make_evidence(self, episode_id: str, obj_id: str) -> dict:
        return {
            "id": obj_id,
            "type": "ReflectionNote",
            "content": "evidence",
            "source_refs": [episode_id],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "episode_id": episode_id,
                "reflection_kind": "success",
                "claims": ["claim1"],
            },
        }

    def test_policy_promotion_requires_min_episodes(self) -> None:
        """Policy promotion requires ≥ POLICY_PROMOTION_MIN_EPISODES episodes."""
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(POLICY_PROMOTION_MIN_EPISODES - 1)
        ]
        decision = assess_policy_promotion(objects)
        assert not decision.promote
        assert str(POLICY_PROMOTION_MIN_EPISODES) in decision.reason

    def test_policy_promotion_succeeds_with_enough_episodes(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(POLICY_PROMOTION_MIN_EPISODES)
        ]
        decision = assess_policy_promotion(objects)
        assert decision.promote
        assert len(decision.supporting_episode_ids) == POLICY_PROMOTION_MIN_EPISODES

    def test_policy_promotion_higher_threshold_than_schema(self) -> None:
        """PolicyNote min_episodes must be ≥ SchemaNote min_episodes (2)."""
        assert POLICY_PROMOTION_MIN_EPISODES >= 2
        # With exactly 2 episodes, schema passes but policy may not.
        two_ep_objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}") for i in range(2)
        ]
        schema_decision = assess_schema_promotion(two_ep_objects)
        policy_decision = assess_policy_promotion(two_ep_objects)
        # PolicyNote threshold is 3; with 2 episodes it should fail if threshold > 2.
        if POLICY_PROMOTION_MIN_EPISODES > 2:
            assert schema_decision.promote
            assert not policy_decision.promote

    def test_policy_promotion_inactive_objects_rejected(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(POLICY_PROMOTION_MIN_EPISODES)
        ]
        objects[0]["status"] = "archived"
        decision = assess_policy_promotion(objects)
        assert not decision.promote

    def test_policy_promotion_stability_score_in_range(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(POLICY_PROMOTION_MIN_EPISODES)
        ]
        decision = assess_policy_promotion(objects)
        assert 0.0 <= decision.stability_score <= 1.0


class TestPreferencePromotion:
    def _make_evidence(self, episode_id: str, obj_id: str) -> dict:
        return {
            "id": obj_id,
            "type": "RawRecord",
            "content": "user expressed preference",
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

    def test_preference_promotion_requires_min_episodes(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(PREFERENCE_PROMOTION_MIN_EPISODES - 1)
        ]
        decision = assess_preference_promotion(objects)
        assert not decision.promote

    def test_preference_promotion_succeeds(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(PREFERENCE_PROMOTION_MIN_EPISODES)
        ]
        decision = assess_preference_promotion(objects)
        assert decision.promote

    def test_preference_promotion_inactive_rejected(self) -> None:
        objects = [
            self._make_evidence(f"ep-{i}", f"obj-{i}")
            for i in range(PREFERENCE_PROMOTION_MIN_EPISODES)
        ]
        objects[-1]["status"] = "deprecated"
        decision = assess_preference_promotion(objects)
        assert not decision.promote


# ─── New offline job kinds ────────────────────────────────────────────────────


class TestNewOfflineJobKinds:
    def test_promote_policy_kind_exists(self) -> None:
        assert OfflineJobKind.PROMOTE_POLICY == "promote_policy"

    def test_promote_preference_kind_exists(self) -> None:
        assert OfflineJobKind.PROMOTE_PREFERENCE == "promote_preference"

    def test_promote_policy_payload(self) -> None:
        payload = PromotePolicyJobPayload(
            target_refs=["obj-1", "obj-2"],
            reason="convergent policy evidence",
        )
        assert len(payload.target_refs) == 2

    def test_promote_preference_payload(self) -> None:
        payload = PromotePreferenceJobPayload(
            target_refs=["obj-1", "obj-2"],
            reason="convergent preference evidence",
        )
        assert len(payload.target_refs) == 2


# ─── Workspace PolicyNote boost ──────────────────────────────────────────────


class TestWorkspacePolicyNoteBoost:
    def test_policy_note_boosted_in_decision_purpose(self) -> None:
        from mind.workspace.builder import _is_decision_purpose

        assert _is_decision_purpose("decision task workspace")
        assert _is_decision_purpose("choose the best strategy")
        assert _is_decision_purpose("evaluate policy options")

    def test_non_decision_purpose_not_boosted(self) -> None:
        from mind.workspace.builder import _is_decision_purpose

        assert not _is_decision_purpose("recall workspace")
        assert not _is_decision_purpose("flash access")
        assert not _is_decision_purpose("reflective workspace")
