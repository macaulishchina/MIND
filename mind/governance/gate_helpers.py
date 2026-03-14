"""Governance gate report I/O and ranking isolation regression helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mind.kernel.retrieval import (
    build_embedding_text,
    build_object_embedding,
    build_search_text,
    search_objects,
)
from mind.primitives.contracts import (
    Capability,
    PrimitiveExecutionContext,
    RetrieveQueryMode,
)

_SCHEMA_VERSION = "governance_gate_report_v1"
_FIXED_TIMESTAMP = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)


def write_governance_gate_report_json(
    path: str | Path,
    result: Any,
) -> Path:
    """Persist the full governance gate result as JSON."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        **asdict(result),
        "h1_pass": result.h1_pass,
        "h2_pass": result.h2_pass,
        "h3_pass": result.h3_pass,
        "h4_pass": result.h4_pass,
        "h5_pass": result.h5_pass,
        "h6_pass": result.h6_pass,
        "h7_pass": result.h7_pass,
        "h8_pass": result.h8_pass,
        "governance_gate_pass": result.governance_gate_pass,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_path


def governance_context(
    *,
    actor: str,
    capabilities: list[Capability],
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=f"governance::{actor}",
        budget_limit=100.0,
        capabilities=capabilities,
    )


def ranking_isolation_regression() -> tuple[bool, bool, bool, int]:
    base_object: dict[str, Any] = {
        "id": "phase-h-ranking-object",
        "type": "RawRecord",
        "content": {"text": "stable retrieval text for phase h ranking checks"},
        "source_refs": [],
        "created_at": _FIXED_TIMESTAMP.isoformat(),
        "updated_at": _FIXED_TIMESTAMP.isoformat(),
        "version": 1,
        "status": "active",
        "priority": 0.4,
        "metadata": {
            "record_kind": "user_message",
            "episode_id": "phase-h-ranking-episode",
            "timestamp_order": 1,
        },
    }
    polluted_object = copy.deepcopy(base_object)
    polluted_object["metadata"]["provenance"] = {
        "session_id": "session-provenance-only",
        "ip_addr": "203.0.113.99",
    }
    polluted_object["metadata"]["governance"] = {
        "conceal": True,
        "operation_id": "op-provenance-only",
    }

    search_text_isolated = build_search_text(base_object) == build_search_text(polluted_object)
    embedding_text_isolated = build_embedding_text(base_object) == build_embedding_text(
        polluted_object
    )
    object_embedding_isolated = build_object_embedding(base_object) == build_object_embedding(
        polluted_object
    )
    provenance_query_hit_count = len(
        search_objects(
            [polluted_object],
            query="session-provenance-only 203.0.113.99",
            query_modes=[RetrieveQueryMode.KEYWORD],
            max_candidates=5,
            object_types=[],
            statuses=[],
            episode_id=None,
            task_id=None,
            query_embedding=None,
            w_priority=0.0,
        )
    )
    return (
        search_text_isolated,
        embedding_text_isolated,
        object_embedding_isolated,
        provenance_query_hit_count,
    )


def assert_governance_gate(result: Any) -> None:
    """Raise :class:`RuntimeError` if any governance hypothesis failed."""

    if not result.h1_pass:
        raise RuntimeError(
            "H-1 failed: direct provenance binding incomplete "
            f"({result.authoritative_binding_count}/{result.raw_object_count})"
        )
    if not result.h2_pass:
        raise RuntimeError(
            "H-2 failed: provenance integrity drift "
            f"(rows={result.direct_provenance_count}, "
            f"duplicates={result.duplicate_provenance_count}, "
            f"orphans={result.orphan_provenance_count}, "
            f"valid_bound_types={result.valid_bound_type_count})"
        )
    if not result.h3_pass:
        raise RuntimeError(
            "H-3 failed: low-privilege provenance isolation drift "
            f"(blocked={result.low_privilege_block_count}/{result.low_privilege_total}, "
            f"clean_reads={result.low_privilege_clean_read_count})"
        )
    if not result.h4_pass:
        raise RuntimeError(
            "H-4 failed: privileged provenance summary leaked or collapsed "
            f"(summaries={result.privileged_summary_count}/{result.privileged_total}, "
            "high_sensitivity_leaks="
            f"{result.privileged_high_sensitivity_leak_count})"
        )
    if not result.h5_pass:
        raise RuntimeError(
            "H-5 failed: online conceal isolation drift "
            f"({result.online_conceal_block_count}/{result.online_conceal_total})"
        )
    if not result.h6_pass:
        raise RuntimeError(
            "H-6 failed: offline conceal isolation drift "
            f"({result.offline_conceal_block_count}/{result.offline_conceal_total})"
        )
    if not result.h7_pass:
        raise RuntimeError(
            "H-7 failed: governance audit chain incomplete "
            f"({result.governance_audit_stage_sequence})"
        )
    if not result.h8_pass:
        raise RuntimeError(
            "H-8 failed: provenance leaked into retrieval/ranking "
            f"(search_text_isolated={result.search_text_isolated}, "
            f"embedding_text_isolated={result.embedding_text_isolated}, "
            f"object_embedding_isolated={result.object_embedding_isolated}, "
            f"provenance_query_hit_count={result.provenance_query_hit_count})"
        )
