#!/usr/bin/env python3
"""Run unified evaluation for one public dataset fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind.app.context import ProviderSelection  # noqa: E402
from mind.fixtures.public_datasets.evaluation import (  # noqa: E402
    evaluate_public_dataset,
    write_public_dataset_evaluation_report_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified evaluation for one public dataset.")
    parser.add_argument("dataset", help="Dataset adapter name, for example locomo.")
    parser.add_argument(
        "--source",
        help="Optional local JSON slice path used instead of the built-in sample fixture.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Optional JSON output path. If omitted, the report is printed to stdout.",
    )
    parser.add_argument("--provider", default=None, help="Optional answer provider.")
    parser.add_argument("--model", default=None, help="Optional answer model.")
    parser.add_argument("--endpoint", default=None, help="Optional provider endpoint override.")
    parser.add_argument("--timeout-ms", type=int, default=None, help="Optional provider timeout.")
    parser.add_argument("--retry-policy", default=None, help="Optional provider retry policy.")
    parser.add_argument(
        "--strategy",
        default="public-dataset",
        help="Long-horizon strategy: fixed, optimized, or public-dataset.",
    )
    args = parser.parse_args()

    provider_selection = _provider_selection_from_namespace(args)

    report = evaluate_public_dataset(
        args.dataset,
        source_path=args.source,
        provider_selection=provider_selection,
        long_horizon_strategy=args.strategy,
    )
    if args.output:
        output_path = write_public_dataset_evaluation_report_json(args.output, report)
        print(f"Wrote report to {output_path}")
        return 0

    print(json.dumps({
        "dataset_name": report.dataset_name,
        "source_path": report.source_path,
        "fixture_name": report.fixture_name,
        "fixture_hash": report.fixture_hash,
        "object_count": report.object_count,
        "retrieval_case_count": report.retrieval_case_count,
        "answer_case_count": report.answer_case_count,
        "long_horizon_sequence_count": report.long_horizon_sequence_count,
        "answer_provider": report.answer_provider,
        "answer_model": report.answer_model,
        "answer_provider_configured": report.answer_provider_configured,
        "long_horizon_strategy": report.long_horizon_strategy,
        "workspace": {
            "case_count": report.workspace.case_count,
            "answer_case_count": report.workspace.answer_case_count,
            "keyword_case_count": report.workspace.keyword_case_count,
            "time_window_case_count": report.workspace.time_window_case_count,
            "vector_case_count": report.workspace.vector_case_count,
            "candidate_recall_at_20": report.workspace.candidate_recall_at_20,
            "workspace_gold_fact_coverage": report.workspace.workspace_gold_fact_coverage,
            "workspace_answer_quality_score": report.workspace.workspace_answer_quality_score,
            "workspace_task_success_rate": report.workspace.workspace_task_success_rate,
            "median_token_cost_ratio": report.workspace.median_token_cost_ratio,
        },
        "long_horizon": {
            "sequence_count": report.long_horizon.sequence_count,
            "average_task_success_rate": report.long_horizon.average_task_success_rate,
            "average_gold_fact_coverage": report.long_horizon.average_gold_fact_coverage,
            "average_reuse_rate": report.long_horizon.average_reuse_rate,
            "average_context_cost_ratio": report.long_horizon.average_context_cost_ratio,
            "average_maintenance_cost_ratio": report.long_horizon.average_maintenance_cost_ratio,
            "average_pollution_rate": report.long_horizon.average_pollution_rate,
            "average_pus": report.long_horizon.average_pus,
        },
        "findings": list(report.findings),
    }, indent=2, sort_keys=True))
    return 0

def _provider_selection_from_namespace(args: argparse.Namespace) -> ProviderSelection | None:
    values = {
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "endpoint": getattr(args, "endpoint", None),
        "timeout_ms": getattr(args, "timeout_ms", None),
        "retry_policy": getattr(args, "retry_policy", None),
    }
    if all(value in (None, "") for value in values.values()):
        return None
    payload = {key: value for key, value in values.items() if value not in (None, "")}
    return ProviderSelection.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(main())