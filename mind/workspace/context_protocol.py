"""Frozen Phase D context serialization protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mind.kernel.schema import strip_control_plane_metadata
from mind.kernel.store import MemoryStore

PHASE_D_CONTEXT_PROTOCOL = "mind.phase_d_context.v1"


@dataclass(frozen=True)
class SerializedContext:
    protocol: str
    kind: str
    object_ids: tuple[str, ...]
    text: str
    token_count: int


def build_raw_topk_context(
    store: MemoryStore,
    object_ids: tuple[str, ...],
) -> SerializedContext:
    payload = {
        "protocol": PHASE_D_CONTEXT_PROTOCOL,
        "kind": "raw_topk",
        "object_ids": list(object_ids),
        "objects": [_raw_object_payload(store.read_object(object_id)) for object_id in object_ids],
    }
    text = _canonical_json(payload)
    return SerializedContext(
        protocol=PHASE_D_CONTEXT_PROTOCOL,
        kind="raw_topk",
        object_ids=object_ids,
        text=text,
        token_count=_token_count(text),
    )


def build_workspace_context(workspace: dict[str, Any]) -> SerializedContext:
    selected_object_ids = tuple(workspace["content"]["selected_object_ids"])
    payload = {
        "protocol": PHASE_D_CONTEXT_PROTOCOL,
        "kind": "workspace",
        "task_id": workspace["metadata"]["task_id"],
        "selected_object_ids": list(selected_object_ids),
        "slots": [
            {
                "summary": slot["summary"],
                "source_refs": slot["source_refs"],
            }
            for slot in workspace["metadata"]["slots"]
        ],
    }
    text = _canonical_json(payload)
    return SerializedContext(
        protocol=PHASE_D_CONTEXT_PROTOCOL,
        kind="workspace",
        object_ids=selected_object_ids,
        text=text,
        token_count=_token_count(text),
    )


def _raw_object_payload(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": obj["id"],
        "type": obj["type"],
        "content": obj["content"],
        "source_refs": obj["source_refs"],
        "metadata": strip_control_plane_metadata(obj["metadata"]),
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _token_count(text: str) -> int:
    if not text:
        return 0
    return len(text.split())
