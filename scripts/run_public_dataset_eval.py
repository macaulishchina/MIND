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
    args = parser.parse_args()

    report = evaluate_public_dataset(args.dataset, source_path=args.source)
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


if __name__ == "__main__":
    raise SystemExit(main())