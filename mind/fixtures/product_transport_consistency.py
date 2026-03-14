"""Product transport consistency scenario fixtures and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProductTransportConsistencyScenario:
    """One frozen semantic scenario shared across product transports."""

    scenario_id: str
    command_family: str
    summary: str
    rest_method: str
    rest_path: str
    rest_json_body: dict[str, Any] | None = None
    mcp_tool_name: str | None = None
    mcp_args: dict[str, Any] = field(default_factory=dict)
    cli_argv: tuple[str, ...] | None = None


def build_product_transport_consistency_scenarios_v1() -> tuple[
    ProductTransportConsistencyScenario, ...
]:
    """Return frozen shared-family consistency scenarios for REST/MCP/CLI audits."""

    scenarios = (
        ProductTransportConsistencyScenario(
            scenario_id="transport-remember-basic",
            command_family="remember",
            summary="Store one memory through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/memories",
            rest_json_body={
                "content": "compare remember",
                "episode_id": "cmp-ep-1",
                "timestamp_order": 1,
            },
            mcp_tool_name="remember",
            mcp_args={
                "content": "compare remember",
                "episode_id": "cmp-ep-1",
                "timestamp_order": 1,
            },
            cli_argv=("mind", "remember", "compare remember", "--episode-id", "cmp-ep-1"),
        ),
        ProductTransportConsistencyScenario(
            scenario_id="transport-recall-keyword",
            command_family="recall",
            summary="Recall seeded memories through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/memories:recall",
            rest_json_body={"query": "seed", "query_modes": ["keyword"]},
            mcp_tool_name="recall",
            mcp_args={"query": "seed", "query_modes": ["keyword"]},
            cli_argv=("mind", "recall", "seed"),
        ),
        ProductTransportConsistencyScenario(
            scenario_id="transport-ask-auto",
            command_family="ask",
            summary="Ask against seeded memories through REST, MCP, and product CLI.",
            rest_method="POST",
            rest_path="/v1/access:ask",
            rest_json_body={"query": "seed"},
            mcp_tool_name="ask_memory",
            mcp_args={"query": "seed"},
            cli_argv=("mind", "ask", "seed"),
        ),
    )
    if len(scenarios) != 3:
        raise RuntimeError(
            f"Product transport consistency scenarios expected 3 entries, got {len(scenarios)}"
        )
    return scenarios


def normalize_product_transport_payload(
    command_family: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Normalize one transport payload for shared semantic comparisons."""

    result = payload.get("result") or {}
    if command_family == "remember":
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
        }
    if command_family == "recall":
        candidates = result.get("candidates") if isinstance(result, dict) else ()
        if not isinstance(candidates, list):
            candidates = ()
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
            "candidate_types": tuple(
                str(candidate.get("object_type") or candidate.get("type") or "unknown")
                for candidate in candidates
                if isinstance(candidate, dict)
            ),
        }
    if command_family == "ask":
        answer_text = result.get("answer_text") if isinstance(result, dict) else None
        support_ids = result.get("answer_support_ids") if isinstance(result, dict) else ()
        if not isinstance(support_ids, list):
            support_ids = ()
        return {
            "status": payload.get("status"),
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else (),
            "resolved_mode": result.get("resolved_mode") if isinstance(result, dict) else None,
            "has_answer_text": isinstance(answer_text, str) and bool(answer_text.strip()),
            "support_count": len(support_ids),
        }
    if command_family == "status":
        if not isinstance(result, dict):
            return {"status": payload.get("status")}
        return {
            "status": payload.get("status"),
            "health": (result.get("health") or {}).get("status"),
            "ready": (result.get("readiness") or {}).get("ready"),
        }
    if command_family == "config":
        if not isinstance(result, dict):
            return {"status": payload.get("status")}
        runtime = result.get("runtime") or {}
        provider = result.get("provider") or {}
        return {
            "status": payload.get("status"),
            "backend": runtime.get("backend"),
            "profile": runtime.get("profile"),
            "provider": provider.get("provider"),
        }
    return payload
