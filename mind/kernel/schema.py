"""Schema validation for memory objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

CORE_OBJECT_TYPES = {
    "RawRecord",
    "TaskEpisode",
    "SummaryNote",
    "ReflectionNote",
    "EntityNode",
    "LinkEdge",
    "WorkspaceView",
    "SchemaNote",
    "FeedbackRecord",
    "PolicyNote",
    "PreferenceNote",
    "ArtifactIndex",
}

REQUIRED_FIELDS = (
    "id",
    "type",
    "content",
    "source_refs",
    "created_at",
    "updated_at",
    "version",
    "status",
    "priority",
    "metadata",
)

REQUIRED_METADATA_FIELDS = {
    "RawRecord": ("record_kind", "episode_id", "timestamp_order"),
    "TaskEpisode": ("task_id", "goal", "result", "success", "record_refs"),
    "SummaryNote": ("summary_scope", "input_refs", "compression_ratio_estimate"),
    "ReflectionNote": ("episode_id", "reflection_kind", "claims"),
    "EntityNode": ("entity_name", "entity_kind", "alias"),
    "LinkEdge": ("confidence", "evidence_refs"),
    "WorkspaceView": ("task_id", "slot_limit", "slots", "selection_policy"),
    "SchemaNote": ("kind", "evidence_refs", "stability_score", "promotion_source_refs"),
    "FeedbackRecord": (
        "task_id",
        "episode_id",
        "query",
        "used_object_ids",
        "helpful_object_ids",
        "unhelpful_object_ids",
        "quality_signal",
    ),
    "PolicyNote": (
        "trigger_condition",
        "action_pattern",
        "evidence_refs",
        "confidence",
        "applies_to_scope",
    ),
    "PreferenceNote": ("preference_key", "preference_value", "strength", "evidence_refs"),
    "ArtifactIndex": (
        "parent_object_id",
        "section_id",
        "heading",
        "summary",
        "depth",
        "content_range",
    ),
}

VALID_STATUS = {"active", "archived", "deprecated", "invalid"}
VALID_RECORD_KIND = {
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "system_event",
}
VALID_REFLECTION_KIND = {"success", "failure", "mixed"}
VALID_SCHEMA_KIND = {"semantic", "procedural"}
VALID_PROPOSAL_STATUS = {"proposed", "verified", "committed", "rejected"}
RESERVED_CONTROL_PLANE_METADATA_FIELDS = frozenset(
    {
        "conceal",
        "direct_provenance_id",
        "direct_provenance_ids",
        "erase",
        "erase_scope",
        "governance",
        "governance_audit",
        "governance_execute",
        "governance_plan",
        "governance_preview",
        "governance_projection",
        "provenance",
        "provenance_footprint",
        "provenance_id",
        "provenance_ids",
        "provenance_ledger",
        "reshape",
        "support_unit",
        "support_units",
    }
)


class SchemaValidationError(ValueError):
    """Raised when an object does not satisfy the frozen schema."""


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_slot(slot: Any, index: int) -> list[str]:
    errors: list[str] = []
    required_slot_fields = (
        "slot_id",
        "summary",
        "evidence_refs",
        "source_refs",
        "reason_selected",
        "priority",
        "expand_pointer",
    )
    if not isinstance(slot, dict):
        return [f"workspace slot {index} must be an object"]

    for field in required_slot_fields:
        if field not in slot:
            errors.append(f"workspace slot {index} missing required field '{field}'")

    if "source_refs" in slot and not isinstance(slot["source_refs"], list):
        errors.append(f"workspace slot {index} source_refs must be a list")
    elif "source_refs" in slot and not slot["source_refs"]:
        errors.append(f"workspace slot {index} source_refs must be non-empty")
    if "evidence_refs" in slot and not isinstance(slot["evidence_refs"], list):
        errors.append(f"workspace slot {index} evidence_refs must be a list")
    elif "evidence_refs" in slot and not slot["evidence_refs"]:
        errors.append(f"workspace slot {index} evidence_refs must be non-empty")
    if "priority" in slot and not isinstance(slot["priority"], int | float):
        errors.append(f"workspace slot {index} priority must be numeric")
    return errors


def strip_control_plane_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return metadata with control-plane fields removed from public/runtime paths."""

    return {
        key: value
        for key, value in metadata.items()
        if key not in RESERVED_CONTROL_PLANE_METADATA_FIELDS
    }


def public_object_view(obj: dict[str, Any]) -> dict[str, Any]:
    """Return the public/runtime-safe view of a memory object."""

    public_obj = dict(obj)
    metadata = public_obj.get("metadata")
    if isinstance(metadata, dict):
        public_obj["metadata"] = strip_control_plane_metadata(metadata)
    return public_obj


def validate_object(obj: dict[str, Any]) -> list[str]:
    """Return a list of schema errors. Empty list means the object is valid."""

    errors: list[str] = []

    if not isinstance(obj, dict):
        return ["object must be a dictionary"]

    for field in REQUIRED_FIELDS:
        if field not in obj:
            errors.append(f"missing required field '{field}'")

    if errors:
        return errors

    object_id = obj["id"]
    object_type = obj["type"]
    content = obj["content"]
    source_refs = obj["source_refs"]
    version = obj["version"]
    status = obj["status"]
    priority = obj["priority"]
    metadata = obj["metadata"]

    if not isinstance(object_id, str) or not object_id:
        errors.append("field 'id' must be a non-empty string")

    if object_type not in CORE_OBJECT_TYPES:
        errors.append(f"field 'type' must be one of {sorted(CORE_OBJECT_TYPES)}")

    if not isinstance(content, str | dict):
        errors.append("field 'content' must be a string or object")

    if not isinstance(source_refs, list) or any(
        not isinstance(item, str) or not item for item in source_refs
    ):
        errors.append("field 'source_refs' must be a list of non-empty strings")

    if not _is_iso_datetime(obj["created_at"]):
        errors.append("field 'created_at' must be an ISO-8601 datetime string")

    if not _is_iso_datetime(obj["updated_at"]):
        errors.append("field 'updated_at' must be an ISO-8601 datetime string")

    if not isinstance(version, int) or version < 1:
        errors.append("field 'version' must be an integer >= 1")

    if status not in VALID_STATUS:
        errors.append(f"field 'status' must be one of {sorted(VALID_STATUS)}")

    if not isinstance(priority, int | float) or not 0 <= float(priority) <= 1:
        errors.append("field 'priority' must be a float in [0, 1]")

    if not isinstance(metadata, dict):
        errors.append("field 'metadata' must be an object")
        return errors

    reserved_metadata_fields = sorted(
        set(metadata).intersection(RESERVED_CONTROL_PLANE_METADATA_FIELDS)
    )
    if reserved_metadata_fields:
        errors.append(f"metadata contains reserved control-plane fields {reserved_metadata_fields}")

    if object_type in REQUIRED_METADATA_FIELDS:
        for field in REQUIRED_METADATA_FIELDS[object_type]:
            if field not in metadata:
                errors.append(f"{object_type} metadata missing required field '{field}'")

    if object_type != "RawRecord" and not source_refs:
        errors.append(f"{object_type} must have non-empty source_refs")

    if object_type == "RawRecord":
        record_kind = metadata.get("record_kind")
        if record_kind not in VALID_RECORD_KIND:
            errors.append(f"RawRecord record_kind must be one of {sorted(VALID_RECORD_KIND)}")
        if "timestamp_order" in metadata and not isinstance(metadata["timestamp_order"], int):
            errors.append("RawRecord metadata.timestamp_order must be an integer")

    if object_type == "TaskEpisode":
        if "success" in metadata and not isinstance(metadata["success"], bool):
            errors.append("TaskEpisode metadata.success must be a boolean")
        if "record_refs" in metadata and not isinstance(metadata["record_refs"], list):
            errors.append("TaskEpisode metadata.record_refs must be a list")

    if object_type == "SummaryNote":
        if "input_refs" in metadata and not isinstance(metadata["input_refs"], list):
            errors.append("SummaryNote metadata.input_refs must be a list")

    if object_type == "ReflectionNote":
        reflection_kind = metadata.get("reflection_kind")
        if reflection_kind not in VALID_REFLECTION_KIND:
            errors.append(
                f"ReflectionNote reflection_kind must be one of {sorted(VALID_REFLECTION_KIND)}"
            )
        if "claims" in metadata and not isinstance(metadata["claims"], list):
            errors.append("ReflectionNote metadata.claims must be a list")

    if object_type == "LinkEdge":
        if not isinstance(content, dict):
            errors.append("LinkEdge content must be an object")
        else:
            for field in ("src_id", "dst_id", "relation_type"):
                if (
                    field not in content
                    or not isinstance(content[field], str)
                    or not content[field]
                ):
                    errors.append(f"LinkEdge content missing non-empty string field '{field}'")
        confidence = metadata.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1
        ):
            errors.append("LinkEdge metadata.confidence must be a float in [0, 1]")
        if "evidence_refs" in metadata and not isinstance(metadata["evidence_refs"], list):
            errors.append("LinkEdge metadata.evidence_refs must be a list")

    if object_type == "WorkspaceView":
        slot_limit = metadata.get("slot_limit")
        if not isinstance(slot_limit, int) or slot_limit < 1:
            errors.append("WorkspaceView metadata.slot_limit must be an integer >= 1")
        slots = metadata.get("slots")
        if not isinstance(slots, list):
            errors.append("WorkspaceView metadata.slots must be a list")
        else:
            if isinstance(slot_limit, int) and len(slots) > slot_limit:
                errors.append("WorkspaceView slot_count must be <= slot_limit")
            for index, slot in enumerate(slots):
                errors.extend(_validate_slot(slot, index))

    if object_type == "SchemaNote":
        kind = metadata.get("kind")
        if kind not in VALID_SCHEMA_KIND:
            errors.append(f"SchemaNote kind must be one of {sorted(VALID_SCHEMA_KIND)}")
        stability_score = metadata.get("stability_score")
        if stability_score is not None and (
            not isinstance(stability_score, int | float) or not 0 <= float(stability_score) <= 1
        ):
            errors.append("SchemaNote metadata.stability_score must be a float in [0, 1]")
        if "evidence_refs" in metadata and not isinstance(metadata["evidence_refs"], list):
            errors.append("SchemaNote metadata.evidence_refs must be a list")
        if "promotion_source_refs" in metadata and not isinstance(
            metadata["promotion_source_refs"], list
        ):
            errors.append("SchemaNote metadata.promotion_source_refs must be a list")
        proposal_status = metadata.get("proposal_status")
        if proposal_status is not None and proposal_status not in VALID_PROPOSAL_STATUS:
            errors.append(
                f"SchemaNote metadata.proposal_status must be one of "
                f"{sorted(VALID_PROPOSAL_STATUS)}"
            )

    if object_type == "EntityNode":
        alias = metadata.get("alias")
        if alias is not None and (
            not isinstance(alias, list)
            or any(not isinstance(item, str) or not item for item in alias)
        ):
            errors.append("EntityNode metadata.alias must be a list of non-empty strings")

    if object_type == "FeedbackRecord":
        quality_signal = metadata.get("quality_signal")
        if quality_signal is not None and (
            not isinstance(quality_signal, int | float) or not -1 <= float(quality_signal) <= 1
        ):
            errors.append("FeedbackRecord metadata.quality_signal must be a float in [-1, 1]")
        for list_field in ("used_object_ids", "helpful_object_ids", "unhelpful_object_ids"):
            value = metadata.get(list_field)
            if value is not None and not isinstance(value, list):
                errors.append(f"FeedbackRecord metadata.{list_field} must be a list")

    if object_type == "PolicyNote":
        confidence = metadata.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1
        ):
            errors.append("PolicyNote metadata.confidence must be a float in [0, 1]")
        if "evidence_refs" in metadata and not isinstance(metadata["evidence_refs"], list):
            errors.append("PolicyNote metadata.evidence_refs must be a list")

    if object_type == "PreferenceNote":
        strength = metadata.get("strength")
        if strength is not None and (
            not isinstance(strength, int | float) or not -1 <= float(strength) <= 1
        ):
            errors.append("PreferenceNote metadata.strength must be a float in [-1, 1]")
        if "evidence_refs" in metadata and not isinstance(metadata["evidence_refs"], list):
            errors.append("PreferenceNote metadata.evidence_refs must be a list")

    if object_type == "ArtifactIndex":
        depth = metadata.get("depth")
        if depth is not None and (not isinstance(depth, int) or depth < 0):
            errors.append("ArtifactIndex metadata.depth must be a non-negative integer")
        content_range = metadata.get("content_range")
        if content_range is not None and not isinstance(content_range, dict):
            errors.append("ArtifactIndex metadata.content_range must be an object")

    return errors


def ensure_valid_object(obj: dict[str, Any]) -> None:
    """Raise if the object does not satisfy the frozen schema."""

    errors = validate_object(obj)
    if errors:
        joined = "; ".join(errors)
        raise SchemaValidationError(joined)
