"""Phase gate and report CLI entry points (benchmarks, strategy, readiness)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .app.context import ProviderSelection
from .capabilities import (
    CapabilityAdapter,
    CapabilityProviderFamily,
    build_capability_adapters_from_environment,
)
from .eval import (
    FixedSummaryMemoryBaselineSystem,
    LongHorizonBenchmarkRunner,
    MindLongHorizonSystem,
    NoMemoryBaselineSystem,
    OptimizedMindStrategy,
    PlainRagBaselineSystem,
    assert_benchmark_comparison,
    assert_benchmark_gate,
    assert_strategy_gate,
    build_benchmark_suite_report,
    evaluate_benchmark_comparison,
    evaluate_benchmark_gate,
    evaluate_fixed_rule_cost_report,
    evaluate_strategy_gate,
    write_benchmark_comparison_report_json,
    write_benchmark_gate_report_json,
    write_benchmark_suite_report_json,
    write_strategy_cost_report_json,
    write_strategy_gate_report_json,
)
from .fixtures.deployment_smoke_suite import (
    evaluate_deployment_smoke_suite,
    write_deployment_smoke_report_json,
    write_deployment_smoke_report_markdown,
)
from .fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from .fixtures.product_readiness_report import (
    assert_product_readiness_report,
    evaluate_product_readiness_report,
    write_product_readiness_report_json,
    write_product_readiness_report_markdown,
)
from .fixtures.public_datasets import (
    evaluate_public_dataset,
    write_public_dataset_evaluation_report_json,
)
from .frontend import (
    assert_frontend_gate,
    evaluate_frontend_gate,
    write_frontend_gate_report_json,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def public_dataset_report_main(argv: Sequence[str] | None = None) -> int:
    """Run unified evaluation for one public dataset fixture."""

    parser = argparse.ArgumentParser(
        prog="mindtest-public-dataset-report",
        description=(
            "Run unified retrieval, workspace, and long-horizon evaluation for one "
            "public dataset fixture."
        ),
    )
    parser.add_argument("dataset", help="Dataset adapter name, for example locomo.")
    parser.add_argument(
        "--source",
        default=None,
        help="Optional local JSON slice path used instead of the built-in sample fixture.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path for the persisted evaluation report.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Optional answer provider, for example openai.",
    )
    parser.add_argument("--model", default=None, help="Optional answer model name.")
    parser.add_argument("--endpoint", default=None, help="Optional provider endpoint override.")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=None,
        help="Optional provider timeout override in milliseconds.",
    )
    parser.add_argument(
        "--retry-policy",
        default=None,
        help="Optional provider retry policy label.",
    )
    parser.add_argument(
        "--strategy",
        default="public-dataset",
        help="Long-horizon strategy: fixed, optimized, or public-dataset.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Apply mind.toml [evaluation] defaults for fields not set via CLI.
    from mind.capabilities.config_file import get_evaluation_config, load_mind_toml

    eval_cfg = get_evaluation_config(load_mind_toml())
    if args.source is None and eval_cfg.get("source"):
        args.source = eval_cfg["source"]
    if args.output is None and eval_cfg.get("output"):
        args.output = eval_cfg["output"]
    if args.strategy == "public-dataset" and eval_cfg.get("strategy"):
        args.strategy = eval_cfg["strategy"]

    provider_selection = _provider_selection_from_namespace(args)
    report = evaluate_public_dataset(
        args.dataset,
        source_path=args.source,
        provider_selection=provider_selection,
        long_horizon_strategy=args.strategy,
    )
    output_path = write_public_dataset_evaluation_report_json(
        args.output or f"artifacts/public_datasets/{args.dataset}_evaluation_report.json",
        report,
    )

    print("Public dataset report")
    print(f"dataset_name={report.dataset_name}")
    if report.source_path is not None:
        print(f"source_path={report.source_path}")
    print(f"report_path={output_path}")
    print(f"fixture_name={report.fixture_name}")
    print(f"fixture_hash={report.fixture_hash}")
    print(f"answer_provider={report.answer_provider}")
    print(f"answer_model={report.answer_model}")
    print(f"answer_provider_configured={str(report.answer_provider_configured).lower()}")
    print(f"long_horizon_strategy={report.long_horizon_strategy}")
    print(f"object_count={report.object_count}")
    print(f"retrieval_case_count={report.retrieval_case_count}")
    print(f"answer_case_count={report.answer_case_count}")
    print(f"long_horizon_sequence_count={report.long_horizon_sequence_count}")
    print(f"candidate_recall_at_20={report.workspace.candidate_recall_at_20:.4f}")
    print(
        "workspace_answer_quality_score="
        f"{report.workspace.workspace_answer_quality_score:.4f}"
    )
    print(f"average_pus={report.long_horizon.average_pus:.4f}")
    print(f"finding_count={len(report.findings)}")
    for index, finding in enumerate(report.findings, start=1):
        print(f"finding_{index}={finding}")
    print("public_dataset_report=PASS")
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


def deployment_smoke_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the deployment smoke report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-deployment-smoke-report",
        description="Run the DeploymentSmokeSuite v1 report against the current repository assets.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/product/deployment_smoke_report.json",
        help="Output path for the persisted deployment smoke JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = evaluate_deployment_smoke_suite(_REPO_ROOT)
    output_path = write_deployment_smoke_report_json(args.output, report)
    markdown_output_path = (
        write_deployment_smoke_report_markdown(
            args.markdown_output,
            report,
            title="Deployment Smoke Report",
        )
        if args.markdown_output
        else None
    )

    print("Deployment smoke report")
    print(f"report_path={output_path}")
    if markdown_output_path is not None:
        print(f"markdown_path={markdown_output_path}")
    print(f"scenario_count={report.scenario_count}")
    print(f"passed_count={report.passed_count}")
    print(f"pass_rate={report.pass_rate:.4f}")
    if report.failure_ids:
        print(f"failure_ids={','.join(report.failure_ids)}")
    print(f"deployment_smoke_report={'PASS' if report.passed else 'FAIL'}")
    return 0


def product_readiness_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the product readiness report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-product-readiness-report",
        description=(
            "Run the aggregated product readiness report across transport, deployment smoke, "
            "and frontend gate assets."
        ),
    )
    parser.add_argument(
        "--output",
        default="artifacts/product/product_readiness_report.json",
        help="Output path for the persisted product readiness JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = evaluate_product_readiness_report(_REPO_ROOT)
    output_path = write_product_readiness_report_json(args.output, report)
    markdown_output_path = (
        write_product_readiness_report_markdown(
            args.markdown_output,
            report,
            title="Product Readiness Report",
        )
        if args.markdown_output
        else None
    )

    print("Product readiness report")
    print(f"report_path={output_path}")
    if markdown_output_path is not None:
        print(f"markdown_path={markdown_output_path}")
    print(f"component_count={report.component_count}")
    print(f"passed_component_count={report.passed_component_count}")
    for component in report.components:
        print(
            f"{component.component_id}="
            f"{'PASS' if component.passed else 'FAIL'}:"
            f"{component.passed_count}/{component.scenario_count}:"
            f"{component.detail}"
        )
    if report.failure_ids:
        print(f"failure_ids={','.join(report.failure_ids)}")
    print(f"product_readiness_report={'PASS' if report.passed else 'FAIL'}")
    return 0


def benchmark_manifest_main() -> int:
    """Print the frozen LongHorizonEval v1 manifest."""

    manifest = build_long_horizon_eval_manifest_v1()
    family_counts = ",".join(f"{family}:{count}" for family, count in manifest.family_counts)
    print("Phase F eval manifest")
    print(f"fixture_name={manifest.fixture_name}")
    print(f"fixture_hash={manifest.fixture_hash}")
    print(f"sequence_count={manifest.sequence_count}")
    print(f"step_range={manifest.min_step_count}..{manifest.max_step_count}")
    print(f"family_counts={family_counts}")
    return 0


def benchmark_baselines_main() -> int:
    """Run the three frozen Phase F baselines once on LongHorizonEval v1."""

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    runs = (
        runner.run_once(system_id="no_memory", system=NoMemoryBaselineSystem()),
        runner.run_once(
            system_id="fixed_summary_memory",
            system=FixedSummaryMemoryBaselineSystem(),
        ),
        runner.run_once(system_id="plain_rag", system=PlainRagBaselineSystem()),
    )

    print("Phase F baseline report")
    print(f"fixture_name={manifest.fixture_name}")
    print(f"fixture_hash={manifest.fixture_hash}")
    print(f"sequence_count={manifest.sequence_count}")
    for run in runs:
        print(f"{run.system_id}_task_success_rate={run.average_task_success_rate:.2f}")
        print(f"{run.system_id}_gold_fact_coverage={run.average_gold_fact_coverage:.2f}")
        print(f"{run.system_id}_reuse_rate={run.average_reuse_rate:.2f}")
        print(f"{run.system_id}_context_cost_ratio={run.average_context_cost_ratio:.2f}")
        print(f"{run.system_id}_maintenance_cost_ratio={run.average_maintenance_cost_ratio:.2f}")
        print(f"{run.system_id}_pollution_rate={run.average_pollution_rate:.2f}")
        print(f"{run.system_id}_pus={run.average_pus:.2f}")
    print("phase_f_baselines=PASS")
    return 0


def benchmark_report_main(argv: Sequence[str] | None = None) -> int:
    """Run repeated Phase F baselines and persist the CI report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-report",
        description="Run repeated Phase F baselines and persist a 95% CI report.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3 for F-3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/baseline_report.json",
        help="Output path for the persisted JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.repeat_count < 3:
        raise SystemExit("--repeat-count must be >= 3.")

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    report = build_benchmark_suite_report(
        runs_by_system={
            "no_memory": runner.run_many(
                system_id="no_memory",
                system=NoMemoryBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
            "fixed_summary_memory": runner.run_many(
                system_id="fixed_summary_memory",
                system=FixedSummaryMemoryBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
            "plain_rag": runner.run_many(
                system_id="plain_rag",
                system=PlainRagBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
        }
    )
    output_path = write_benchmark_suite_report_json(args.output, report)

    print("Phase F CI report")
    print(f"fixture_name={report.fixture_name}")
    print(f"fixture_hash={report.fixture_hash}")
    print(f"repeat_count={report.repeat_count}")
    print(f"report_path={output_path}")
    for system_report in report.system_reports:
        print(f"{system_report.system_id}_pus_mean={system_report.pus.mean:.2f}")
        print(
            f"{system_report.system_id}_pus_ci="
            f"{system_report.pus.ci_lower:.2f}..{system_report.pus.ci_upper:.2f}"
        )
        print(
            f"{system_report.system_id}_task_success_ci="
            f"{system_report.task_success_rate.ci_lower:.2f}"
            f"..{system_report.task_success_rate.ci_upper:.2f}"
        )
    print("phase_f_report=PASS")
    return 0


def benchmark_comparison_main(argv: Sequence[str] | None = None) -> int:
    """Run the current MIND system against the Phase F baselines."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-comparison",
        description="Run Phase F benchmark comparison for F-4 ~ F-6.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/comparison_report.json",
        help="Output path for the persisted comparison JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_benchmark_comparison(repeat_count=args.repeat_count)
    try:
        assert_benchmark_comparison(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_benchmark_comparison_report_json(args.output, result)
    mind_report = next(
        system_report
        for system_report in result.suite_report.system_reports
        if system_report.system_id == "mind"
    )
    print("Phase F comparison report")
    print(f"fixture_name={result.suite_report.fixture_name}")
    print(f"fixture_hash={result.suite_report.fixture_hash}")
    print(f"repeat_count={result.suite_report.repeat_count}")
    print(f"report_path={output_path}")
    print(f"mind_pus_mean={mind_report.pus.mean:.2f}")
    print(
        "mind_vs_no_memory_diff="
        f"{result.versus_no_memory.mean_diff:.2f}"
        f" ({result.versus_no_memory.ci_lower:.2f}..{result.versus_no_memory.ci_upper:.2f})"
    )
    print(
        "mind_vs_fixed_summary_memory_diff="
        f"{result.versus_fixed_summary_memory.mean_diff:.2f}"
        f" ({result.versus_fixed_summary_memory.ci_lower:.2f}"
        f"..{result.versus_fixed_summary_memory.ci_upper:.2f})"
    )
    print(
        "mind_vs_plain_rag_diff="
        f"{result.versus_plain_rag.mean_diff:.2f}"
        f" ({result.versus_plain_rag.ci_lower:.2f}..{result.versus_plain_rag.ci_upper:.2f})"
    )
    print(f"F-2={'PASS' if result.f2_pass else 'FAIL'}")
    print(f"F-3={'PASS' if result.f3_pass else 'FAIL'}")
    print(f"F-4={'PASS' if result.f4_pass else 'FAIL'}")
    print(f"F-5={'PASS' if result.f5_pass else 'FAIL'}")
    print(f"F-6={'PASS' if result.f6_pass else 'FAIL'}")
    print(f"phase_f_comparison={'PASS' if result.benchmark_comparison_pass else 'FAIL'}")
    return 0


def benchmark_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the full local Phase F gate, including F-7 ablations."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-gate",
        description="Run the full local Phase F gate.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/gate_report.json",
        help="Output path for the persisted gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_benchmark_gate(repeat_count=args.repeat_count)
    try:
        assert_benchmark_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_benchmark_gate_report_json(args.output, result)
    print("Phase F gate report")
    print(f"manifest_hash={result.manifest_hash}")
    print(f"manifest_step_range={result.manifest_min_step_count}..{result.manifest_max_step_count}")
    print(f"repeat_count={result.comparison_result.suite_report.repeat_count}")
    print(f"report_path={output_path}")
    print(f"mind_vs_no_memory_diff={result.comparison_result.versus_no_memory.mean_diff:.2f}")
    print(
        "mind_vs_fixed_summary_memory_diff="
        f"{result.comparison_result.versus_fixed_summary_memory.mean_diff:.2f}"
    )
    print(f"mind_vs_plain_rag_diff={result.comparison_result.versus_plain_rag.mean_diff:.2f}")
    print(f"workspace_ablation_drop={result.workspace_ablation.mean_diff:.2f}")
    print(f"offline_maintenance_ablation_drop={result.offline_maintenance_ablation.mean_diff:.2f}")
    print(f"F-1={'PASS' if result.f1_pass else 'FAIL'}")
    print(f"F-2={'PASS' if result.f2_pass else 'FAIL'}")
    print(f"F-3={'PASS' if result.f3_pass else 'FAIL'}")
    print(f"F-4={'PASS' if result.f4_pass else 'FAIL'}")
    print(f"F-5={'PASS' if result.f5_pass else 'FAIL'}")
    print(f"F-6={'PASS' if result.f6_pass else 'FAIL'}")
    print(f"F-7={'PASS' if result.f7_pass else 'FAIL'}")
    print(f"phase_f_gate={'PASS' if result.benchmark_gate_pass else 'FAIL'}")
    return 0


def strategy_cost_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase G fixed-rule strategy cost report skeleton."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-cost-report",
        description="Run the Phase G fixed-rule strategy cost report skeleton.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for cost accounting. Must be >= 1.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_g/cost_report.json",
        help="Output path for the persisted Phase G cost report JSON.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_fixed_rule_cost_report(repeat_count=args.repeat_count)
    output_path = write_strategy_cost_report_json(args.output, result)
    print("Phase G cost report")
    print(f"fixture_name={result.fixture_name}")
    print(f"fixture_hash={result.fixture_hash}")
    print(f"strategy_id={result.strategy_id}")
    print(f"repeat_count={result.repeat_count}")
    print(f"report_path={output_path}")
    print(f"token_cost_ratio={result.token_cost_ratio.mean:.2f}")
    print(f"storage_cost_ratio={result.storage_cost_ratio.mean:.2f}")
    print(f"maintenance_cost_ratio={result.maintenance_cost_ratio.mean:.2f}")
    print(f"total_cost_ratio={result.total_cost_ratio.mean:.2f}")
    print(f"total_budget_ratio={result.budget_profile.total_budget_ratio:.2f}")
    print(f"total_budget_bias={result.total_budget_bias.mean:.2f}")
    print("phase_g_cost_report=PASS")
    return 0


def strategy_dev_main(argv: Sequence[str] | None = None) -> int:
    """Run a local fixed-rule vs optimized-v1 dev comparison."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-strategy-dev",
        description="Run a Phase G dev comparison between fixed-rule and optimized_v1.",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=1,
        help="Deterministic run id used by both systems.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )
    fixed_system = MindLongHorizonSystem()
    optimized_system = MindLongHorizonSystem(strategy=OptimizedMindStrategy())
    try:
        fixed_run = runner.run_once(
            system_id="mind_fixed_rule",
            system=fixed_system,
            run_id=args.run_id,
        )
        optimized_run = runner.run_once(
            system_id="mind_optimized_v1",
            system=optimized_system,
            run_id=args.run_id,
        )
        fixed_snapshot = fixed_system.cost_snapshot(args.run_id)
        optimized_snapshot = optimized_system.cost_snapshot(args.run_id)
    finally:
        fixed_system.close()
        optimized_system.close()

    print("Phase G strategy dev report")
    print(f"fixture_name={fixed_run.fixture_name}")
    print(f"fixture_hash={fixed_run.fixture_hash}")
    print(f"run_id={args.run_id}")
    print(f"fixed_rule_pus={fixed_run.average_pus:.2f}")
    print(f"optimized_v1_pus={optimized_run.average_pus:.2f}")
    print(f"pus_delta={optimized_run.average_pus - fixed_run.average_pus:.2f}")
    print(f"fixed_rule_context_cost_ratio={fixed_run.average_context_cost_ratio:.2f}")
    print(f"optimized_v1_context_cost_ratio={optimized_run.average_context_cost_ratio:.2f}")
    print(f"fixed_rule_storage_cost_ratio={fixed_snapshot.storage_cost_ratio:.2f}")
    print(f"optimized_v1_storage_cost_ratio={optimized_snapshot.storage_cost_ratio:.2f}")
    print(
        "phase_g_strategy_dev="
        f"{'PASS' if optimized_run.average_pus > fixed_run.average_pus else 'FAIL'}"
    )
    return 0


def strategy_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the formal Phase G local gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-gate",
        description="Run the full local Phase G strategy optimization gate.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_g/gate_report.json",
        help="Output path for the persisted Phase G gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_strategy_gate(repeat_count=args.repeat_count)
    try:
        assert_strategy_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_strategy_gate_report_json(args.output, result)
    print("Phase G gate report")
    print(f"manifest_hash={result.manifest_hash}")
    print(f"repeat_count={result.repeat_count}")
    print(f"report_path={output_path}")
    print(f"pus_improvement={result.pus_improvement.mean_diff:.2f}")
    for family_result in result.family_improvements:
        print(f"{family_result.family}_pus_delta={family_result.pus_delta.mean_diff:.2f}")
    print(f"token_budget_bias={result.optimized_cost_report.token_budget_bias.mean:.2f}")
    print(f"storage_budget_bias={result.optimized_cost_report.storage_budget_bias.mean:.2f}")
    print(
        f"maintenance_budget_bias={result.optimized_cost_report.maintenance_budget_bias.mean:.2f}"
    )
    print(f"total_budget_bias={result.optimized_cost_report.total_budget_bias.mean:.2f}")
    print(f"pollution_rate_delta={result.pollution_rate_delta.mean_diff:.2f}")
    print(f"G-1={'PASS' if result.g1_pass else 'FAIL'}")
    print(f"G-2={'PASS' if result.g2_pass else 'FAIL'}")
    print(f"G-3={'PASS' if result.g3_pass else 'FAIL'}")
    print(f"G-4={'PASS' if result.g4_pass else 'FAIL'}")
    print(f"G-5={'PASS' if result.g5_pass else 'FAIL'}")
    print(f"phase_g_gate={'PASS' if result.strategy_gate_pass else 'FAIL'}")
    return 0


def _build_live_capability_adapters(
    requested_providers: Sequence[str],
) -> list[CapabilityAdapter]:
    families = _requested_live_provider_families(requested_providers)
    adapters = build_capability_adapters_from_environment(provider_families=families or None)
    if not families:
        return adapters
    available_families = {adapter.descriptor.provider_family for adapter in adapters}
    missing = [family.value for family in families if family not in available_families]
    if missing:
        raise SystemExit(
            "Missing configured auth for live providers: " + ", ".join(sorted(missing))
        )
    return adapters


def _requested_live_provider_families(
    requested_providers: Sequence[str],
) -> tuple[CapabilityProviderFamily, ...]:
    seen: set[CapabilityProviderFamily] = set()
    ordered_families: list[CapabilityProviderFamily] = []
    for provider in requested_providers:
        family = CapabilityProviderFamily(provider)
        if family in seen:
            continue
        seen.add(family)
        ordered_families.append(family)
    return tuple(ordered_families)


def _format_live_provider_summary(adapters: Sequence[CapabilityAdapter]) -> str:
    live_providers = [
        adapter.descriptor.provider_family.value
        for adapter in adapters
        if adapter.descriptor.provider_family is not CapabilityProviderFamily.DETERMINISTIC
    ]
    return ",".join(live_providers) if live_providers else "none"


def frontend_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase M frontend-experience gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-m-gate",
        description="Run the local Phase M frontend-experience gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_m/gate_report.json",
        help="Output path for the persisted Phase M gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_frontend_gate()

    try:
        assert_frontend_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_frontend_gate_report_json(args.output, result)
    print("Phase M gate report")
    print(f"report_path={output_path}")
    print(f"flow_report={result.flow_report.passed_count}/{result.flow_report.scenario_count}")
    print(
        "responsive_audit="
        f"{result.responsive_audit.passed_count}/{result.responsive_audit.scenario_count}"
    )
    print(
        "dev_mode_audit="
        f"{result.dev_mode_audit.passed_count}/{result.dev_mode_audit.scenario_count}"
    )
    print(
        "product_transport_audit="
        f"coverage:{result.product_transport_audit.coverage:.4f},"
        f"rest_mcp:{result.product_transport_audit.rest_mcp_pass_rate:.4f},"
        f"rest_cli:{result.product_transport_audit.rest_cli_pass_rate:.4f}"
    )
    print(f"M-1={'PASS' if result.m1_pass else 'FAIL'}")
    print(f"M-2={'PASS' if result.m2_pass else 'FAIL'}")
    print(f"M-3={'PASS' if result.m3_pass else 'FAIL'}")
    print(f"M-4={'PASS' if result.m4_pass else 'FAIL'}")
    print(f"M-5={'PASS' if result.m5_pass else 'FAIL'}")
    print(f"M-6={'PASS' if result.m6_pass else 'FAIL'}")
    print(f"phase_m_gate={'PASS' if result.frontend_gate_pass else 'FAIL'}")
    return 0


def product_readiness_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the aggregated product readiness gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-product-readiness-gate",
        description="Run the aggregated product readiness gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/product/product_readiness_gate.json",
        help="Output path for the persisted product readiness gate JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown gate summary.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = evaluate_product_readiness_report(_REPO_ROOT)
    output_path = write_product_readiness_report_json(args.output, report)
    markdown_output_path = (
        write_product_readiness_report_markdown(
            args.markdown_output,
            report,
            title="Product Readiness Gate",
        )
        if args.markdown_output
        else None
    )

    try:
        assert_product_readiness_report(report)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Product readiness gate")
    print(f"report_path={output_path}")
    if markdown_output_path is not None:
        print(f"markdown_path={markdown_output_path}")
    print(f"component_count={report.component_count}")
    print(f"passed_component_count={report.passed_component_count}")
    for component in report.components:
        print(
            f"{component.component_id}="
            f"{'PASS' if component.passed else 'FAIL'}:"
            f"{component.passed_count}/{component.scenario_count}:"
            f"{component.detail}"
        )
    print(f"product_readiness_gate={'PASS' if report.passed else 'FAIL'}")
    return 0
