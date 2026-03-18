"""Run the end-to-end memory lifecycle benchmark and persist artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from mind.app.context import ProviderSelection
from mind.eval import (
    evaluate_memory_lifecycle_benchmark,
    write_memory_lifecycle_benchmark_report_json,
)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the benchmark, and persist report artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Dataset name label used in the report")
    parser.add_argument("--source", required=True, help="Path to a local slice JSON file")
    parser.add_argument("--output", required=True, help="Path for the benchmark JSON report")
    parser.add_argument(
        "--telemetry-output",
        help="Path for JSONL telemetry. Defaults next to the report.",
    )
    parser.add_argument(
        "--store-output",
        help="Path for the SQLite benchmark store. Defaults next to the report.",
    )
    parser.add_argument("--provider", default="stub", help="Capability provider name")
    parser.add_argument("--model", default="deterministic", help="Capability model name")
    parser.add_argument("--endpoint", help="Optional provider endpoint override")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Provider timeout in ms")
    parser.add_argument("--retry-policy", default="default", help="Provider retry policy")
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    artifact_root = output_path.parent
    telemetry_path = Path(args.telemetry_output) if args.telemetry_output else artifact_root / (
        output_path.stem + ".telemetry.jsonl"
    )
    store_path = Path(args.store_output) if args.store_output else artifact_root / (
        output_path.stem + ".sqlite3"
    )
    provider_selection = ProviderSelection(
        provider=args.provider,
        model=args.model,
        endpoint=args.endpoint,
        timeout_ms=args.timeout_ms,
        retry_policy=args.retry_policy,
    )

    report = evaluate_memory_lifecycle_benchmark(
        args.dataset,
        source_path=args.source,
        provider_selection=provider_selection,
        telemetry_path=telemetry_path,
        store_path=store_path,
    )
    write_memory_lifecycle_benchmark_report_json(output_path, report)

    final_stage = report.stage_reports[-1]
    print("Memory lifecycle benchmark")
    print(f"dataset={report.dataset_name}")
    print(f"run_id={report.run_id}")
    print(f"report_path={output_path}")
    print(f"telemetry_path={telemetry_path}")
    print(f"store_path={store_path}")
    print(f"stages={len(report.stage_reports)}")
    print(f"final_average_answer_quality={final_stage.ask.average_answer_quality}")
    print(f"final_candidate_hit_rate={final_stage.ask.candidate_hit_rate}")
    print(f"final_pollution_rate={final_stage.ask.pollution_rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())