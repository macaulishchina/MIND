"""CLI subcommands for offline operations, configuration, and reports."""

from __future__ import annotations

import argparse
import os

from .cli import (
    _ACCEPTANCE_REPORTS,
    _LIVE_CAPABILITY_PROVIDER_CHOICES,
    _REPO_ROOT,
    _add_common_resolution_args,
    _run_forwarded_command,
    _run_no_argv_command,
)
from .cli_config import (
    CliProfile,
    ResolvedCliConfig,
    build_config_doctor_checks,
    list_cli_profiles,
    redact_dsn,
    resolve_cli_config,
)
from .cli_gates import (
    capability_compatibility_report_main,
    offline_worker_main,
    product_transport_report_main,
)
from .cli_phase_gates import (
    benchmark_baselines_main,
    benchmark_comparison_main,
    benchmark_manifest_main,
    benchmark_report_main,
    deployment_smoke_report_main,
    product_readiness_report_main,
    public_dataset_report_main,
    strategy_cost_report_main,
)
from .kernel.postgres_store import (
    PostgresMemoryStore,
)
from .offline import (
    OfflineJobKind,
    OfflineJobStatus,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    new_offline_job,
    select_replay_targets,
)


def _require_postgres_dsn(dsn: str | None) -> str:
    if dsn:
        return dsn
    env_dsn = os.environ.get("MIND_POSTGRES_DSN")
    if env_dsn:
        return env_dsn
    raise SystemExit("Provide --dsn or set MIND_POSTGRES_DSN.")


def _run_list_offline_jobs(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    statuses = [OfflineJobStatus(status) for status in args.status]
    with PostgresMemoryStore(dsn) as store:
        jobs = store.iter_offline_jobs(statuses=statuses)

    print("Offline jobs")
    print(f"job_count={len(jobs)}")
    for index, job in enumerate(jobs, start=1):
        print(
            f"job_{index}={job.job_id}:{job.job_kind.value}:{job.status.value}:{job.priority:.2f}"
        )
    return 0


def _run_offline_worker_command(args: argparse.Namespace) -> int:
    forwarded = [
        "--dsn",
        _require_postgres_dsn(args.dsn),
        "--max-jobs",
        str(args.max_jobs),
        "--worker-id",
        str(args.worker_id),
    ]
    for job_kind in args.job_kind:
        forwarded.extend(("--job-kind", str(job_kind)))
    return offline_worker_main(forwarded)


def _run_enqueue_reflect_episode(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    payload = ReflectEpisodeJobPayload(
        episode_id=args.episode_id,
        focus=args.focus,
    )
    job = new_offline_job(
        job_kind=OfflineJobKind.REFLECT_EPISODE,
        payload=payload,
        priority=args.priority,
        max_attempts=args.max_attempts,
    )
    with PostgresMemoryStore(dsn) as store:
        store.enqueue_offline_job(job)

    print("Offline reflect_episode job enqueued")
    print(f"job_id={job.job_id}")
    print(f"episode_id={payload.episode_id}")
    print(f"priority={job.priority:.2f}")
    print(f"max_attempts={job.max_attempts}")
    return 0


def _run_enqueue_promote_schema(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    payload = PromoteSchemaJobPayload(
        target_refs=list(args.target_ref),
        reason=args.reason,
    )
    job = new_offline_job(
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload=payload,
        priority=args.priority,
        max_attempts=args.max_attempts,
    )
    with PostgresMemoryStore(dsn) as store:
        store.enqueue_offline_job(job)

    print("Offline promote_schema job enqueued")
    print(f"job_id={job.job_id}")
    print(f"target_count={len(payload.target_refs)}")
    print(f"priority={job.priority:.2f}")
    print(f"max_attempts={job.max_attempts}")
    return 0


def _run_offline_replay(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    if args.top_k < 1:
        raise SystemExit("--top-k must be >= 1.")

    with PostgresMemoryStore(dsn) as store:
        candidate_ids = tuple(args.candidate_id)
        candidate_source = "explicit"
        if args.episode_id:
            candidate_ids = tuple(
                record["id"] for record in store.raw_records_for_episode(args.episode_id)
            )
            candidate_source = f"episode:{args.episode_id}"
        if not candidate_ids:
            raise SystemExit("Provide --candidate-id or --episode-id.")
        ranking = select_replay_targets(
            store,
            candidate_ids,
            top_k=min(args.top_k, len(candidate_ids)),
        )

    print("Offline replay ranking")
    print(f"candidate_source={candidate_source}")
    print(f"candidate_count={len(candidate_ids)}")
    print(f"selected_count={len(ranking)}")
    for index, target in enumerate(ranking, start=1):
        print(f"target_{index}={target.object_id}:{target.score:.4f}")
    return 0


def _configure_offline_commands(command_parser: argparse.ArgumentParser) -> None:
    offline_subparsers = command_parser.add_subparsers(
        dest="offline_command",
        metavar="offline-command",
    )

    worker_parser = offline_subparsers.add_parser(
        "worker",
        help="Run one offline maintenance worker batch.",
        description="Run one offline maintenance worker batch against PostgreSQL.",
    )
    worker_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    worker_parser.add_argument(
        "--max-jobs",
        type=int,
        default=1,
        help="Maximum number of jobs to claim in this batch.",
    )
    worker_parser.add_argument(
        "--worker-id",
        default="mind-offline-worker",
        help="Worker identifier to stamp on claimed jobs.",
    )
    worker_parser.add_argument(
        "--job-kind",
        action="append",
        choices=[job_kind.value for job_kind in OfflineJobKind],
        default=[],
        help="Optional job kind filter. May be passed multiple times.",
    )
    worker_parser.set_defaults(_mind_handler=_run_offline_worker_command)

    list_jobs_parser = offline_subparsers.add_parser(
        "list-jobs",
        help="Inspect offline jobs currently persisted in PostgreSQL.",
        description="Inspect offline jobs currently persisted in PostgreSQL.",
    )
    list_jobs_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    list_jobs_parser.add_argument(
        "--status",
        action="append",
        choices=[status.value for status in OfflineJobStatus],
        default=[],
        help="Optional job status filter. May be passed multiple times.",
    )
    list_jobs_parser.set_defaults(_mind_handler=_run_list_offline_jobs)

    reflect_episode_parser = offline_subparsers.add_parser(
        "reflect-episode",
        help="Enqueue one reflect_episode offline job.",
        description="Enqueue one reflect_episode offline job into PostgreSQL.",
    )
    reflect_episode_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    reflect_episode_parser.add_argument("--episode-id", required=True, help="Target episode id.")
    reflect_episode_parser.add_argument(
        "--focus",
        default="offline replay reflection",
        help="Reflection focus stored in the queued payload.",
    )
    reflect_episode_parser.add_argument(
        "--priority",
        type=float,
        default=0.5,
        help="Job priority in the [0, 1] range.",
    )
    reflect_episode_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum offline worker attempts for the queued job.",
    )
    reflect_episode_parser.set_defaults(_mind_handler=_run_enqueue_reflect_episode)

    promote_schema_parser = offline_subparsers.add_parser(
        "promote-schema",
        help="Enqueue one promote_schema offline job.",
        description="Enqueue one promote_schema offline job into PostgreSQL.",
    )
    promote_schema_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    promote_schema_parser.add_argument(
        "--target-ref",
        action="append",
        required=True,
        default=[],
        help="Target object id to include in the promotion job. May be passed multiple times.",
    )
    promote_schema_parser.add_argument(
        "--reason",
        required=True,
        help="Human-readable reason stored in the queued payload.",
    )
    promote_schema_parser.add_argument(
        "--priority",
        type=float,
        default=0.5,
        help="Job priority in the [0, 1] range.",
    )
    promote_schema_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum offline worker attempts for the queued job.",
    )
    promote_schema_parser.set_defaults(_mind_handler=_run_enqueue_promote_schema)

    replay_parser = offline_subparsers.add_parser(
        "replay",
        help="Inspect replay target ranking for a candidate pool.",
        description="Inspect replay target ranking for a candidate pool in PostgreSQL.",
    )
    replay_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    replay_parser.add_argument(
        "--candidate-id",
        action="append",
        default=[],
        help="Candidate object id to rank. May be passed multiple times.",
    )
    replay_parser.add_argument(
        "--episode-id",
        help="Optional episode id used to derive candidate raw records.",
    )
    replay_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of ranked replay targets to print.",
    )
    replay_parser.set_defaults(_mind_handler=_run_offline_replay)


def _resolve_cli_config_from_args(args: argparse.Namespace) -> ResolvedCliConfig:
    return resolve_cli_config(
        profile=getattr(args, "profile", None),
        backend=getattr(args, "backend", None),
        sqlite_path=getattr(args, "sqlite_path", None),
        postgres_dsn=getattr(args, "dsn", None),
        allow_sqlite=True,
    )


def _run_config_show(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    print("CLI config")
    print(f"requested_profile={config.requested_profile.value}")
    print(f"requested_profile_source={config.requested_profile_source}")
    print(f"resolved_profile={config.resolved_profile.value}")
    print(f"backend={config.backend.value}")
    print(f"backend_source={config.backend_source}")
    if config.sqlite_path is not None and config.sqlite_path_source is not None:
        print(f"sqlite_path={config.sqlite_path.as_posix()}")
        print(f"sqlite_path_source={config.sqlite_path_source}")
    if config.postgres_dsn is not None and config.postgres_dsn_source is not None:
        print(f"postgres_dsn={redact_dsn(config.postgres_dsn)}")
        print(f"postgres_dsn_source={config.postgres_dsn_source}")
    elif config.postgres_dsn_source is not None:
        print("postgres_dsn=unset")
        print(f"postgres_dsn_source={config.postgres_dsn_source}")
    return 0


def _run_config_profile(args: argparse.Namespace) -> int:
    profiles = list_cli_profiles()
    selected_name = getattr(args, "name", None)
    if selected_name is not None:
        selected_profile = CliProfile(selected_name)
        profiles = tuple(profile for profile in profiles if profile.profile is selected_profile)

    print("CLI profiles")
    print(f"profile_count={len(profiles)}")
    for index, profile in enumerate(profiles, start=1):
        env_hint = profile.env_hint or "none"
        print(
            f"profile_{index}="
            f"{profile.profile.value}:{profile.default_backend.value}:{env_hint}:{profile.description}"
        )
    return 0


def _run_config_doctor(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    checks = build_config_doctor_checks(config)
    overall_status = "ok" if all(check.status == "ok" for check in checks) else "warn"
    print("CLI config doctor")
    print(f"overall_status={overall_status}")
    for index, check in enumerate(checks, start=1):
        print(f"check_{index}={check.name}:{check.status}:{check.detail}")
    return 0


def _configure_config_commands(command_parser: argparse.ArgumentParser) -> None:
    config_subparsers = command_parser.add_subparsers(
        dest="config_command",
        metavar="config-command",
    )

    show_parser = config_subparsers.add_parser(
        "show",
        help="Resolve and print the active CLI config.",
        description="Resolve and print the active CLI profile/backend configuration.",
    )
    _add_common_resolution_args(show_parser)
    show_parser.set_defaults(_mind_handler=_run_config_show)

    profile_parser = config_subparsers.add_parser(
        "profile",
        help="Inspect the frozen CLI profile catalog.",
        description="Inspect the frozen CLI profile catalog.",
    )
    profile_parser.add_argument(
        "--name",
        choices=[profile.value for profile in CliProfile],
        help="Optional single profile to inspect.",
    )
    profile_parser.set_defaults(_mind_handler=_run_config_profile)

    doctor_parser = config_subparsers.add_parser(
        "doctor",
        help="Run a lightweight CLI config diagnostic.",
        description="Run a lightweight CLI config diagnostic.",
    )
    _add_common_resolution_args(doctor_parser)
    doctor_parser.set_defaults(_mind_handler=_run_config_doctor)


def _run_acceptance_report(args: argparse.Namespace) -> int:
    phase = args.phase
    report_path = _ACCEPTANCE_REPORTS[phase]
    relative_path = report_path.relative_to(_REPO_ROOT)
    print("Acceptance report")
    print(f"phase={phase}")
    print(f"report_path={relative_path}")
    print(f"exists={'true' if report_path.exists() else 'false'}")
    return 0


def _run_public_dataset_report(args: argparse.Namespace) -> int:
    forwarded = [str(args.dataset)]
    if args.source is not None:
        forwarded.extend(("--source", str(args.source)))
    if args.output is not None:
        forwarded.extend(("--output", str(args.output)))
    return public_dataset_report_main(forwarded)


def _configure_report_commands(command_parser: argparse.ArgumentParser) -> None:
    report_subparsers = command_parser.add_subparsers(
        dest="report_command",
        metavar="report-command",
    )

    phase_f_manifest_parser = report_subparsers.add_parser(
        "phase-f-manifest",
        help="Print the frozen LongHorizonEval v1 manifest.",
        description="Print the frozen LongHorizonEval v1 manifest.",
    )
    phase_f_manifest_parser.set_defaults(
        _mind_handler=_run_no_argv_command(benchmark_manifest_main)
    )

    phase_f_baselines_parser = report_subparsers.add_parser(
        "phase-f-baselines",
        help="Run the three frozen Phase F baselines once.",
        description="Run the three frozen Phase F baselines once on LongHorizonEval v1.",
    )
    phase_f_baselines_parser.set_defaults(
        _mind_handler=_run_no_argv_command(benchmark_baselines_main)
    )

    phase_f_ci_parser = report_subparsers.add_parser(
        "phase-f-ci",
        help="Run repeated Phase F baselines and persist the CI report.",
        description="Run repeated Phase F baselines and persist the CI report.",
    )
    phase_f_ci_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3 for F-3.",
    )
    phase_f_ci_parser.add_argument(
        "--output",
        default="artifacts/phase_f/baseline_report.json",
        help="Output path for the persisted JSON report.",
    )
    phase_f_ci_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            benchmark_report_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_f_comparison_parser = report_subparsers.add_parser(
        "phase-f-comparison",
        help="Run the Phase F comparison report.",
        description="Run the current MIND system against the Phase F baselines.",
    )
    phase_f_comparison_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    phase_f_comparison_parser.add_argument(
        "--output",
        default="artifacts/phase_f/comparison_report.json",
        help="Output path for the persisted comparison JSON report.",
    )
    phase_f_comparison_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            benchmark_comparison_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_g_cost_parser = report_subparsers.add_parser(
        "phase-g-cost",
        help="Run the Phase G cost report.",
        description="Run the Phase G fixed-rule strategy cost report skeleton.",
    )
    phase_g_cost_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for cost accounting. Must be >= 1.",
    )
    phase_g_cost_parser.add_argument(
        "--output",
        default="artifacts/phase_g/cost_report.json",
        help="Output path for the persisted Phase G cost report JSON.",
    )
    phase_g_cost_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            strategy_cost_report_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_k_compatibility_parser = report_subparsers.add_parser(
        "phase-k-compatibility",
        help="Run the Phase K provider compatibility report.",
        description="Run the Phase K provider compatibility report.",
    )
    phase_k_compatibility_parser.add_argument(
        "--output",
        default="artifacts/phase_k/provider_compatibility.json",
        help="Output path for the persisted Phase K compatibility JSON report.",
    )
    phase_k_compatibility_parser.add_argument(
        "--live-provider",
        action="append",
        choices=_LIVE_CAPABILITY_PROVIDER_CHOICES,
        default=[],
        help=(
            "Optional live provider adapter to execute during the report."
            " May be passed multiple times."
        ),
    )
    phase_k_compatibility_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            capability_compatibility_report_main,
            (("output", "--output"), ("live_provider", "--live-provider")),
        )
    )

    product_transport_parser = report_subparsers.add_parser(
        "product-transport",
        help="Run the product transport audit report.",
        description="Run the shared REST / MCP / product CLI transport audit report.",
    )
    product_transport_parser.add_argument(
        "--output",
        default="artifacts/product/transport_audit_report.json",
        help="Output path for the persisted product transport audit JSON report.",
    )
    product_transport_parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    product_transport_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            product_transport_report_main,
            (("output", "--output"), ("markdown_output", "--markdown-output")),
        )
    )

    deployment_smoke_parser = report_subparsers.add_parser(
        "deployment-smoke",
        help="Run the deployment smoke report.",
        description="Run the DeploymentSmokeSuite v1 report against the current repository assets.",
    )
    deployment_smoke_parser.add_argument(
        "--output",
        default="artifacts/product/deployment_smoke_report.json",
        help="Output path for the persisted deployment smoke JSON report.",
    )
    deployment_smoke_parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    deployment_smoke_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            deployment_smoke_report_main,
            (("output", "--output"), ("markdown_output", "--markdown-output")),
        )
    )

    product_readiness_parser = report_subparsers.add_parser(
        "product-readiness",
        help="Run the product readiness report.",
        description=(
            "Run the aggregated product readiness report across transport, deployment smoke, "
            "and frontend gate assets."
        ),
    )
    product_readiness_parser.add_argument(
        "--output",
        default="artifacts/product/product_readiness_report.json",
        help="Output path for the persisted product readiness JSON report.",
    )
    product_readiness_parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    product_readiness_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            product_readiness_report_main,
            (("output", "--output"), ("markdown_output", "--markdown-output")),
        )
    )

    public_dataset_parser = report_subparsers.add_parser(
        "public-dataset",
        help="Run the unified public-dataset evaluation report.",
        description=(
            "Run unified retrieval, workspace, and long-horizon evaluation for one "
            "public dataset fixture."
        ),
    )
    public_dataset_parser.add_argument(
        "dataset",
        help="Dataset adapter name, for example locomo.",
    )
    public_dataset_parser.add_argument(
        "--source",
        default=None,
        help="Optional local JSON slice path used instead of the built-in sample fixture.",
    )
    public_dataset_parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path for the persisted evaluation report.",
    )
    public_dataset_parser.set_defaults(_mind_handler=_run_public_dataset_report)

    acceptance_parser = report_subparsers.add_parser(
        "acceptance",
        help="Inspect the frozen acceptance-report path for a phase.",
        description="Inspect the frozen acceptance-report path for a phase.",
    )
    acceptance_parser.add_argument(
        "--phase",
        choices=sorted(_ACCEPTANCE_REPORTS),
        required=True,
        help="Phase identifier with a frozen acceptance report.",
    )
    acceptance_parser.set_defaults(_mind_handler=_run_acceptance_report)


