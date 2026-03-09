"""Schema validation for Phase B memory objects."""

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
    if "evidence_refs" in slot and not isinstance(slot["evidence_refs"], list):
        errors.append(f"workspace slot {index} evidence_refs must be a list")
    if "priority" in slot and not isinstance(slot["priority"], int | float):
        errors.append(f"workspace slot {index} priority must be numeric")
    return errors


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
        if "evidence_refs" in metadata and not isinstance(metadata["evidence_refs"], list):
            errors.append("LinkEdge metadata.evidence_refs must be a list")

    if object_type == "WorkspaceView":
        slots = metadata.get("slots")
        if not isinstance(slots, list):
            errors.append("WorkspaceView metadata.slots must be a list")
        else:
            for index, slot in enumerate(slots):
                errors.extend(_validate_slot(slot, index))

    if object_type == "SchemaNote":
        kind = metadata.get("kind")
        if kind not in VALID_SCHEMA_KIND:
            errors.append(f"SchemaNote kind must be one of {sorted(VALID_SCHEMA_KIND)}")

    return errors


def ensure_valid_object(obj: dict[str, Any]) -> None:
    """Raise if the object does not satisfy the frozen schema."""

    errors = validate_object(obj)
    if errors:
        joined = "; ".join(errors)
        raise SchemaValidationError(joined)
