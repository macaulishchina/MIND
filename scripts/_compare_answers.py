#!/usr/bin/env python3
"""Compare stub vs LLM answers side-by-side for all datasets."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from mind.capabilities.config import resolve_capability_provider_config
    from mind.capabilities.service import CapabilityService
    from mind.fixtures.public_datasets import (
        build_public_dataset_answer_cases,
        build_public_dataset_objects,
        build_public_dataset_retrieval_cases,
    )
    from mind.kernel.retrieval import build_query_embedding
    from mind.kernel.store import SQLiteMemoryStore
    from mind.primitives.contracts import (
        PrimitiveExecutionContext,
        PrimitiveOutcome,
        RetrieveResponse,
    )
    from mind.primitives.service import PrimitiveService
    from mind.workspace.answer_benchmark import (
        answer_from_raw_topk,
        answer_from_workspace,
        score_answer,
    )
    from mind.workspace.builder import WorkspaceBuilder, WorkspaceBuildError
    from mind.workspace.context_protocol import (
        build_raw_topk_context,
        build_workspace_context,
    )

    stub_svc = CapabilityService(
        provider_config=resolve_capability_provider_config(
            config_file={"provider": "stub"}, env={}
        )
    )
    llm_svc = CapabilityService(provider_config=resolve_capability_provider_config())

    print(
        f"LLM config: provider={llm_svc.provider_config.provider}  "
        f"model={llm_svc.provider_config.model}  "
        f"endpoint={llm_svc.provider_config.endpoint}"
    )
    print(f"Auth configured: {llm_svc.provider_config.auth.is_configured()}")

    for dataset_name in ["scifact", "hotpotqa", "locomo"]:
        source = f"artifacts/dev/public_datasets/{dataset_name}_raw_compiled_slice.json"
        objects = build_public_dataset_objects(dataset_name, source_path=source)
        retrieval_cases = build_public_dataset_retrieval_cases(dataset_name, source_path=source)
        answer_cases = build_public_dataset_answer_cases(dataset_name, source_path=source)
        answer_case_map = {case.case_id: case for case in answer_cases}

        print(f"\n{'=' * 72}")
        print(f"  DATASET: {dataset_name.upper()}")
        print(f"{'=' * 72}")

        with tempfile.TemporaryDirectory(prefix="compare_") as tmpdir:
            with SQLiteMemoryStore(Path(tmpdir) / "workspace.sqlite3") as store:
                store.insert_objects(objects)
                service = PrimitiveService(store, query_embedder=build_query_embedding)
                builder = WorkspaceBuilder(store)

                for retrieval_case in retrieval_cases:
                    answer_case = answer_case_map.get(retrieval_case.case_id)
                    if answer_case is None:
                        continue

                    result = service.retrieve(
                        {
                            "query": retrieval_case.query,
                            "query_modes": [mode.value for mode in retrieval_case.query_modes],
                            "budget": {"max_cost": 1000.0, "max_candidates": 20},
                            "filters": retrieval_case.filters,
                        },
                        PrimitiveExecutionContext(
                            actor="compare",
                            budget_scope_id=f"compare::{retrieval_case.case_id}",
                        ),
                    )
                    response = (
                        RetrieveResponse.model_validate(result.response)
                        if result.outcome is PrimitiveOutcome.SUCCESS and result.response
                        else None
                    )
                    if response is None:
                        print(f"\n  [SKIP] {retrieval_case.case_id}: retrieval failed")
                        continue

                    candidate_ids = list(response.candidate_ids)
                    raw_top20 = tuple(candidate_ids[:20])
                    raw_ctx = build_raw_topk_context(store, raw_top20)
                    workspace_result: Any | None
                    try:
                        workspace_result = builder.build(
                            task_id=retrieval_case.task_id,
                            candidate_ids=candidate_ids,
                            candidate_scores=list(response.scores),
                            slot_limit=retrieval_case.slot_limit,
                            workspace_id=f"compare-{retrieval_case.case_id}",
                        )
                    except WorkspaceBuildError:
                        workspace_result = None

                    workspace_ctx = (
                        build_workspace_context(workspace_result.workspace)
                        if workspace_result is not None
                        else None
                    )

                    print(f"\n  Question:       {answer_case.prompt}")
                    print(f"  Kind:           {answer_case.answer_kind}")
                    print(f"  Required frags: {answer_case.required_fragments}")

                    _print_answer_block(
                        label="Raw top-k context",
                        stub_answer=answer_from_raw_topk(
                            answer_case,
                            raw_ctx,
                            capability_service=stub_svc,
                        ),
                        llm_answer=answer_from_raw_topk(
                            answer_case,
                            raw_ctx,
                            capability_service=llm_svc,
                        ),
                        answer_case=answer_case,
                        score_answer=score_answer,
                    )

                    if workspace_ctx is not None:
                        _print_answer_block(
                            label="Workspace context",
                            stub_answer=answer_from_workspace(
                                answer_case,
                                workspace_ctx,
                                capability_service=stub_svc,
                            ),
                            llm_answer=answer_from_workspace(
                                answer_case,
                                workspace_ctx,
                                capability_service=llm_svc,
                            ),
                            answer_case=answer_case,
                            score_answer=score_answer,
                        )
    return 0


def _print_answer_block(
    *,
    label: str,
    stub_answer: Any,
    llm_answer: Any,
    answer_case: Any,
    score_answer: Any,
) -> None:
    stub_score = score_answer(answer_case, stub_answer)
    llm_score = score_answer(answer_case, llm_answer)
    print(f"\n  [{label}]")
    print(f"    STUB answer: {stub_answer.text}")
    print(
        f"    STUB score:  quality={stub_score.answer_quality_score:.4f}"
        f"  task_comp={stub_score.task_completion_score:.4f}"
    )
    print(f"    LLM  answer: {llm_answer.text}")
    print(
        f"    LLM  score:  quality={llm_score.answer_quality_score:.4f}"
        f"  task_comp={llm_score.task_completion_score:.4f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
