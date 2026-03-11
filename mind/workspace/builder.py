"""WorkspaceView builder."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mind.kernel.schema import ensure_valid_object
from mind.kernel.store import MemoryStore, StoreError
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

InaccessibleWorkspaceStatuses = {"invalid"}


class WorkspaceBuildError(RuntimeError):
    """Raised when a workspace cannot be built safely from candidates."""


@dataclass(frozen=True)
class WorkspaceBuildResult:
    workspace: dict[str, Any]
    selected_ids: tuple[str, ...]
    skipped_ids: tuple[str, ...]


class WorkspaceBuilder:
    """Construct a valid WorkspaceView from retrieval candidates."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry_recorder = telemetry_recorder

    def build(
        self,
        *,
        task_id: str,
        candidate_ids: list[str],
        candidate_scores: list[float] | None = None,
        slot_limit: int = 4,
        selection_policy: str = "retrieval-score-then-priority",
        purpose: str = "task workspace",
        workspace_id: str | None = None,
        dev_mode: bool = False,
        telemetry_run_id: str | None = None,
        telemetry_operation_id: str | None = None,
        telemetry_parent_event_id: str | None = None,
    ) -> WorkspaceBuildResult:
        if not task_id:
            raise WorkspaceBuildError("task_id must be non-empty")
        if slot_limit < 1:
            raise WorkspaceBuildError("slot_limit must be >= 1")
        if not candidate_ids:
            raise WorkspaceBuildError("candidate_ids must be non-empty")
        if candidate_scores is not None and len(candidate_scores) != len(candidate_ids):
            raise WorkspaceBuildError("candidate_scores must align with candidate_ids")

        resolved_workspace_id = workspace_id or f"workspace-{task_id}"
        run_id = telemetry_run_id or resolved_workspace_id
        operation_id = telemetry_operation_id or resolved_workspace_id
        self._record_telemetry(
            enabled=dev_mode,
            event=TelemetryEvent(
                event_id=f"{operation_id}-entry",
                scope=TelemetryScope.WORKSPACE,
                kind=TelemetryEventKind.ENTRY,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=telemetry_parent_event_id,
                workspace_id=resolved_workspace_id,
                payload={
                    "task_id": task_id,
                    "candidate_ids": list(candidate_ids),
                    "candidate_scores": list(candidate_scores or []),
                    "selection_policy": selection_policy,
                    "purpose": purpose,
                },
                debug_fields={
                    "candidate_count": len(candidate_ids),
                    "slot_limit": slot_limit,
                },
            ),
        )

        deduped_candidates = self._dedupe_candidates(candidate_ids, candidate_scores)
        ranked_candidates: list[tuple[dict[str, Any], float]] = []
        skipped_ids: list[str] = []

        for object_id, score in deduped_candidates:
            try:
                obj = self.store.read_object(object_id)
            except StoreError as exc:
                raise WorkspaceBuildError(f"candidate '{object_id}' not found") from exc

            if self._is_object_concealed(object_id):
                skipped_ids.append(object_id)
                continue
            if obj["status"] in InaccessibleWorkspaceStatuses:
                skipped_ids.append(object_id)
                continue

            ranked_candidates.append((obj, score))

        if not ranked_candidates:
            raise WorkspaceBuildError("no accessible candidates available for workspace")

        ranked_candidates.sort(
            key=lambda item: (
                item[1],
                float(item[0]["priority"]),
                item[0]["updated_at"],
                item[0]["id"],
            ),
            reverse=True,
        )
        selected = ranked_candidates[:slot_limit]

        slots = [
            self._build_slot(index=index + 1, obj=obj, retrieval_score=score)
            for index, (obj, score) in enumerate(selected)
        ]
        selected_ids = tuple(obj["id"] for obj, _ in selected)
        self._record_telemetry(
            enabled=dev_mode,
            event=TelemetryEvent(
                event_id=f"{operation_id}-selection",
                scope=TelemetryScope.WORKSPACE,
                kind=TelemetryEventKind.DECISION,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=f"{operation_id}-entry",
                workspace_id=resolved_workspace_id,
                payload={
                    "selected_ids": list(selected_ids),
                    "skipped_ids": list(skipped_ids),
                    "ranked_candidates": [
                        {
                            "object_id": obj["id"],
                            "score": round(score, 4),
                            "priority": float(obj["priority"]),
                            "type": obj["type"],
                        }
                        for obj, score in ranked_candidates
                    ],
                },
                debug_fields={
                    "selected_count": len(selected_ids),
                    "skipped_count": len(skipped_ids),
                    "deduped_candidate_count": len(deduped_candidates),
                },
            ),
        )
        now = self._clock().isoformat()
        workspace = {
            "id": resolved_workspace_id,
            "type": "WorkspaceView",
            "content": {
                "purpose": purpose,
                "selected_object_ids": list(selected_ids),
                "candidate_count": len(candidate_ids),
            },
            "source_refs": list(selected_ids),
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "status": "active",
            "priority": max(slot["priority"] for slot in slots),
            "metadata": {
                "task_id": task_id,
                "slot_limit": slot_limit,
                "slots": slots,
                "selection_policy": selection_policy,
            },
        }
        ensure_valid_object(workspace)
        self._record_telemetry(
            enabled=dev_mode,
            event=TelemetryEvent(
                event_id=f"{operation_id}-result",
                scope=TelemetryScope.WORKSPACE,
                kind=TelemetryEventKind.CONTEXT_RESULT,
                occurred_at=self._clock(),
                run_id=run_id,
                operation_id=operation_id,
                parent_event_id=f"{operation_id}-selection",
                workspace_id=resolved_workspace_id,
                payload={
                    "workspace_object": workspace,
                },
                debug_fields={
                    "slot_count": len(slots),
                    "workspace_priority": workspace["priority"],
                },
            ),
        )
        return WorkspaceBuildResult(
            workspace=workspace,
            selected_ids=selected_ids,
            skipped_ids=tuple(skipped_ids),
        )

    def _build_slot(
        self,
        *,
        index: int,
        obj: dict[str, Any],
        retrieval_score: float,
    ) -> dict[str, Any]:
        evidence_refs = self._evidence_refs(obj)
        slot_priority = round(min(1.0, max(float(obj["priority"]), retrieval_score)), 4)
        return {
            "slot_id": f"slot-{index}",
            "summary": self._slot_summary(obj),
            "evidence_refs": evidence_refs,
            "source_refs": [obj["id"]],
            "reason_selected": (
                f"retrieval_score={retrieval_score:.4f}; "
                f"object_priority={float(obj['priority']):.4f}"
            ),
            "priority": slot_priority,
            "expand_pointer": {"object_id": obj["id"]},
        }

    @staticmethod
    def _dedupe_candidates(
        candidate_ids: list[str],
        candidate_scores: list[float] | None,
    ) -> list[tuple[str, float]]:
        ranked: dict[str, float] = {}
        if candidate_scores is None:
            candidate_scores = [0.0] * len(candidate_ids)
        for object_id, score in zip(candidate_ids, candidate_scores, strict=True):
            previous = ranked.get(object_id)
            if previous is None or score > previous:
                ranked[object_id] = float(score)
        return list(ranked.items())

    @staticmethod
    def _slot_summary(obj: dict[str, Any]) -> str:
        object_type = obj["type"]
        content = obj["content"]

        if isinstance(content, dict):
            if object_type == "SummaryNote":
                return str(content.get("summary", obj["id"]))
            if object_type == "ReflectionNote":
                return str(content.get("summary", obj["id"]))
            if object_type == "TaskEpisode":
                title = content.get("title", obj["id"])
                result = obj.get("metadata", {}).get("result")
                return f"{title} [{result}]"
            if object_type == "RawRecord":
                text = content.get("text")
                if isinstance(text, str) and text:
                    return text
            if object_type == "LinkEdge":
                src_id = content.get("src_id", "?")
                relation = content.get("relation_type", "?")
                dst_id = content.get("dst_id", "?")
                return f"{src_id} {relation} {dst_id}"
            if object_type == "EntityNode":
                name = obj.get("metadata", {}).get("entity_name", obj["id"])
                description = content.get("description", "")
                return f"{name}: {description}".strip(": ")
            if object_type == "SchemaNote":
                rule = content.get("rule")
                if isinstance(rule, str) and rule:
                    return rule
            if object_type == "WorkspaceView":
                purpose = content.get("purpose", "workspace")
                return f"workspace: {purpose}"
            return json.dumps(content, ensure_ascii=True, sort_keys=True)

        return str(content)

    @staticmethod
    def _evidence_refs(obj: dict[str, Any]) -> list[str]:
        metadata = obj.get("metadata", {})
        candidate_fields = (
            metadata.get("evidence_refs"),
            metadata.get("record_refs"),
            metadata.get("input_refs"),
            obj.get("source_refs"),
        )
        for value in candidate_fields:
            if isinstance(value, list) and value:
                return [str(item) for item in value]
        return [obj["id"]]

    def _is_object_concealed(self, object_id: str) -> bool:
        check = getattr(self.store, "is_object_concealed", None)
        if check is None:
            return False
        return bool(check(object_id))

    def _record_telemetry(
        self,
        *,
        enabled: bool,
        event: TelemetryEvent,
    ) -> None:
        if not enabled or self._telemetry_recorder is None:
            return
        self._telemetry_recorder.record(event)
