from __future__ import annotations

import tomllib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from mind.cli import _command_group_lookup, build_mind_parser, mind_main
from mind.fixtures import build_mind_cli_scenario_set_v1
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    ReplayTarget,
    new_offline_job,
)
from mind.primitives import PrimitiveExecutionResult, PrimitiveName, PrimitiveOutcome


def test_pyproject_contains_split_product_and_dev_entries() -> None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    assert "mind" in scripts, "pyproject.toml is missing the product mind entry point"
    assert "mindtest" in scripts, "pyproject.toml is missing the dev mindtest entry point"
    assert scripts["mind"] == "mind.product_cli:product_main"
    assert scripts["mindtest"] == "mind.cli:mind_main"


def test_top_level_help_covers_all_phase_j_command_groups(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_mind_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["-h"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    for command_name in _command_group_lookup():
        assert command_name in output
    assert "Unified CLI" in output
    assert "mindtest primitive -h" in output


@pytest.mark.parametrize(
    ("command_name", "expected_fragment"),
    [
        ("primitive", "write-raw"),
        ("access", "run --mode flash"),
        ("offline", "offline worker"),
        ("governance", "plan-conceal"),
        ("gate", "phase-b"),
        ("report", "phase-f-ci"),
        ("demo", "ingest-read"),
        ("config", "config show"),
    ],
)
def test_family_help_is_available_without_nested_implementation(
    command_name: str,
    expected_fragment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main([command_name])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert expected_fragment in output


def test_mind_cli_scenario_set_v1_is_frozen_and_complete() -> None:
    scenarios = build_mind_cli_scenario_set_v1()

    assert len(scenarios) == 26
    assert {scenario.command_family for scenario in scenarios} == {
        "help",
        "primitive",
        "access",
        "offline",
        "governance",
        "gate",
        "report",
        "demo",
        "config",
    }
    assert scenarios[0].argv == ("mind", "-h")
    assert any(scenario.argv == ("mind", "gate", "phase-i") for scenario in scenarios)
    assert any(
        scenario.argv == ("mind", "report", "acceptance", "--phase", "h") for scenario in scenarios
    )


def test_access_help_lists_real_access_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["access"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "run" in output
    assert "benchmark" in output


def test_access_run_flash_with_seeded_fixtures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_access_flash.sqlite3"

    exit_code = mind_main(
        [
            "access",
            "run",
            "--sqlite-path",
            str(db_path),
            "--seed-bench-fixtures",
            "--mode",
            "flash",
            "--task-id",
            "task-001",
            "--task-family",
            "speed_sensitive",
            "--time-budget-ms",
            "150",
            "--episode-id",
            "episode-001",
            "--query",
            "For episode-001, reply with only success or failure.",
            "--hard-constraint",
            "must answer with only success or failure",
            "--hard-constraint",
            "must stay within 2 tokens",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "requested_mode=flash" in output
    assert "resolved_mode=flash" in output
    assert "context_kind=raw_topk" in output
    assert "seeded_fixture_count=" in output
    assert "candidate_count=" in output
    assert "trace_1=select_mode:flash:initial:explicit_mode_request:0" in output


def test_access_run_auto_can_jump_to_reflective_access(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_access_auto.sqlite3"

    exit_code = mind_main(
        [
            "access",
            "run",
            "--sqlite-path",
            str(db_path),
            "--seed-bench-fixtures",
            "--mode",
            "auto",
            "--task-id",
            "task-004",
            "--task-family",
            "high_correctness",
            "--time-budget-ms",
            "1500",
            "--episode-id",
            "episode-004",
            "--query",
            "For episode-004, explain the failed revalidation signal.",
            "--hard-constraint",
            "must identify whether the episode succeeded or failed",
            "--hard-constraint",
            "must include the failure or revalidation signal when present",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "requested_mode=auto" in output
    assert "resolved_mode=reflective_access" in output
    assert "context_kind=workspace" in output
    assert "verification_note_count=" in output
    assert "trace_1=select_mode:reconstruct:initial:constraint_risk:0" in output
    assert "select_mode:reflective_access:jump:evidence_conflict:0" in output


def test_access_benchmark_prints_frontier_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    aggregates = tuple(
        SimpleNamespace(
            requested_mode=SimpleNamespace(value=f"mode_{index}"),
            task_family=SimpleNamespace(value=f"family_{index}"),
            answer_quality_score=0.8,
            cost_efficiency_score=0.9,
            time_budget_hit_rate=1.0,
        )
        for index in range(15)
    )
    frontier_comparisons = (
        SimpleNamespace(
            task_family=SimpleNamespace(value="speed_sensitive"),
            family_best_fixed_mode=SimpleNamespace(value="flash"),
            auto_aqs=0.8,
            auto_cost_efficiency_score=0.9,
            auto_aqs_drop=0.1,
        ),
        SimpleNamespace(
            task_family=SimpleNamespace(value="balanced"),
            family_best_fixed_mode=SimpleNamespace(value="recall"),
            auto_aqs=0.8,
            auto_cost_efficiency_score=0.9,
            auto_aqs_drop=0.1,
        ),
        SimpleNamespace(
            task_family=SimpleNamespace(value="high_correctness"),
            family_best_fixed_mode=SimpleNamespace(value="reflective_access"),
            auto_aqs=0.8,
            auto_cost_efficiency_score=0.9,
            auto_aqs_drop=0.1,
        ),
    )
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.evaluate_access_benchmark",
        lambda *args, **kwargs: SimpleNamespace(
            case_count=60,
            run_count=300,
            mode_family_aggregates=aggregates,
            frontier_comparisons=frontier_comparisons,
        ),
    )

    exit_code = mind_main(["access", "benchmark"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "backend=sqlite" in output
    assert "storage_scope=isolated" in output
    assert "case_count=60" in output
    assert "run_count=300" in output
    assert "aggregate_count=15" in output
    assert "frontier_count=3" in output
    assert "speed_sensitive" in output
    assert "high_correctness" in output


def test_access_benchmark_uses_isolated_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    @contextmanager
    def fake_temporary_postgres_database(dsn: str, prefix: str) -> Iterator[str]:
        captured["admin_dsn"] = dsn
        captured["prefix"] = prefix
        yield "postgresql+psycopg://temp-db"

    def fake_run_postgres_migrations(dsn: str) -> None:
        captured["migrated_dsn"] = dsn

    def fake_build_postgres_store_factory(dsn: str) -> object:
        captured["factory_dsn"] = dsn
        return f"factory:{dsn}"

    def fake_evaluate_access_benchmark(db_path: Path, store_factory: object) -> object:
        captured["db_path"] = db_path
        captured["store_factory"] = store_factory
        return SimpleNamespace(
            case_count=60,
            run_count=300,
            mode_family_aggregates=(
                SimpleNamespace(
                    requested_mode=SimpleNamespace(value="flash"),
                    task_family=SimpleNamespace(value="speed_sensitive"),
                    answer_quality_score=0.8,
                    cost_efficiency_score=0.9,
                    time_budget_hit_rate=1.0,
                ),
            ),
            frontier_comparisons=(
                SimpleNamespace(
                    task_family=SimpleNamespace(value="speed_sensitive"),
                    family_best_fixed_mode=SimpleNamespace(value="flash"),
                    auto_aqs=0.75,
                    auto_cost_efficiency_score=0.95,
                    auto_aqs_drop=0.05,
                ),
            ),
        )

    monkeypatch.setattr(
        "mind.cli_primitive_cmds.temporary_postgres_database",
        fake_temporary_postgres_database,
    )
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.run_postgres_migrations",
        fake_run_postgres_migrations,
    )
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.build_postgres_store_factory",
        fake_build_postgres_store_factory,
    )
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.evaluate_access_benchmark",
        fake_evaluate_access_benchmark,
    )

    exit_code = mind_main(
        [
            "access",
            "benchmark",
            "--backend",
            "postgresql",
            "--dsn",
            "postgresql+psycopg://user:secret@host/mind",
        ]
    )

    assert exit_code == 0
    assert captured["admin_dsn"] == "postgresql+psycopg://user:secret@host/mind"
    assert captured["prefix"] == "mind_access_benchmark"
    assert captured["migrated_dsn"] == "postgresql+psycopg://temp-db"
    assert captured["factory_dsn"] == "postgresql+psycopg://temp-db"
    assert captured["store_factory"] == "factory:postgresql+psycopg://temp-db"
    output = capsys.readouterr().out
    assert "backend=postgresql" in output
    assert "storage_scope=isolated" in output


def _extract_output_value(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1]
    raise AssertionError(f"missing output line for {key!r}")


def _seed_task_episode(store_path: Path, *, episode_id: str, success: bool = True) -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC).isoformat()
    seed_raw_id = f"{episode_id}-seed-raw"
    with SQLiteMemoryStore(store_path) as store:
        store.insert_object(
            {
                "id": seed_raw_id,
                "type": "RawRecord",
                "content": "seed episode evidence",
                "source_refs": [],
                "created_at": now,
                "updated_at": now,
                "version": 1,
                "status": "active",
                "priority": 0.4,
                "metadata": {
                    "record_kind": "system_event",
                    "episode_id": episode_id,
                    "timestamp_order": 1,
                },
            }
        )
        store.insert_object(
            {
                "id": episode_id,
                "type": "TaskEpisode",
                "content": {"goal": "cli task", "result": "done"},
                "source_refs": [seed_raw_id],
                "created_at": now,
                "updated_at": now,
                "version": 1,
                "status": "active",
                "priority": 0.6,
                "metadata": {
                    "task_id": "task-cli",
                    "goal": "cli task",
                    "result": "done",
                    "success": success,
                    "record_refs": [seed_raw_id],
                },
            }
        )


def test_governance_help_lists_real_governance_subcommands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main(["governance"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "plan-conceal" in output
    assert "preview" in output
    assert "execute-conceal" in output


def test_governance_conceal_flow_round_trips_through_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_governance.sqlite3"

    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "episode-gov-1",
                "--timestamp-order",
                "1",
                "--content",
                "governance note one",
                "--provenance-json",
                (
                    '{"producer_kind":"user","producer_id":"cli-user","captured_at":"2026-03-10T12:00:00Z",'
                    '"source_channel":"chat","tenant_id":"tenant-a","user_id":"user-a",'
                    '"ip_addr":"10.0.0.1","episode_id":"episode-gov-1"}'
                ),
            ]
        )
        == 0
    )
    first_output = capsys.readouterr().out
    object_id_a = _extract_output_value(first_output, "object_id")

    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "assistant_message",
                "--episode-id",
                "episode-gov-1",
                "--timestamp-order",
                "2",
                "--content",
                "governance note two",
                "--provenance-json",
                (
                    '{"producer_kind":"model","producer_id":"cli-model","captured_at":"2026-03-10T12:01:00Z",'
                    '"source_channel":"chat","tenant_id":"tenant-a","model_id":"model-a",'
                    '"model_provider":"openai","ip_addr":"10.0.0.2","episode_id":"episode-gov-1"}'
                ),
            ]
        )
        == 0
    )
    second_output = capsys.readouterr().out
    object_id_b = _extract_output_value(second_output, "object_id")

    plan_exit = mind_main(
        [
            "governance",
            "plan-conceal",
            "--sqlite-path",
            str(db_path),
            "--episode-id",
            "episode-gov-1",
            "--reason",
            "conceal governance episode",
        ]
    )

    assert plan_exit == 0
    plan_output = capsys.readouterr().out
    operation_id = _extract_output_value(plan_output, "operation_id")
    assert "candidate_count=2" in plan_output
    assert '"episode_id":"episode-gov-1"' in plan_output

    preview_exit = mind_main(
        [
            "governance",
            "preview",
            "--sqlite-path",
            str(db_path),
            "--operation-id",
            operation_id,
        ]
    )

    assert preview_exit == 0
    preview_output = capsys.readouterr().out
    assert "candidate_count=2" in preview_output
    assert "provenance_summary_count=2" in preview_output
    assert "ip_addr" not in preview_output
    assert "summary_1=" in preview_output

    execute_exit = mind_main(
        [
            "governance",
            "execute-conceal",
            "--sqlite-path",
            str(db_path),
            "--operation-id",
            operation_id,
        ]
    )

    assert execute_exit == 0
    execute_output = capsys.readouterr().out
    assert "concealed_count=2" in execute_output
    assert f"concealed_1={object_id_a}" in execute_output
    assert f"concealed_2={object_id_b}" in execute_output

    read_exit = mind_main(
        [
            "primitive",
            "read",
            "--sqlite-path",
            str(db_path),
            "--object-id",
            object_id_a,
        ]
    )

    assert read_exit == 1
    read_output = capsys.readouterr().out
    assert "error_code=object_inaccessible" in read_output
    assert "visibility" in read_output


def test_demo_help_lists_real_demo_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["demo"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "ingest-read" in output
    assert "access-run" in output
    assert "offline-job" in output


def test_demo_ingest_read_runs_with_default_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main(["demo", "ingest-read"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "backend=sqlite" in output
    assert "storage_scope=isolated" in output
    assert "write_outcome=success" in output
    assert "read_outcome=success" in output
    assert "read_object_count=1" in output
    assert '"remember this"' in output


def test_demo_access_run_runs_with_default_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main(["demo", "access-run"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "backend=sqlite" in output
    assert "storage_scope=isolated" in output
    assert "case_id=" in output
    assert "requested_mode=auto" in output
    assert "resolved_mode=" in output
    assert "trace_event_count=" in output
    assert "trace_1=select_mode:" in output


def test_demo_offline_job_uses_isolated_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    class _DemoPostgresStore:
        def __init__(self) -> None:
            self.jobs: list[OfflineJob] = []

        def __enter__(self) -> _DemoPostgresStore:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def enqueue_offline_job(self, job: OfflineJob) -> None:
            self.jobs.append(job)

        def iter_offline_jobs(
            self,
            *,
            statuses: Sequence[OfflineJobStatus] = (),
        ) -> list[OfflineJob]:
            if statuses:
                allowed = set(statuses)
                return [job for job in self.jobs if job.status in allowed]
            return list(self.jobs)

    fake_store = _DemoPostgresStore()

    @contextmanager
    def fake_temporary_postgres_database(dsn: str, prefix: str) -> Iterator[str]:
        captured["admin_dsn"] = dsn
        captured["prefix"] = prefix
        yield "postgresql+psycopg://temp-demo-db"

    def fake_run_postgres_migrations(dsn: str) -> None:
        captured["migrated_dsn"] = dsn

    monkeypatch.setattr(
        "mind.cli_demo_cmds.temporary_postgres_database",
        fake_temporary_postgres_database,
    )
    monkeypatch.setattr("mind.cli_demo_cmds.run_postgres_migrations", fake_run_postgres_migrations)
    monkeypatch.setattr("mind.cli_demo_cmds.PostgresMemoryStore", lambda dsn: fake_store)

    exit_code = mind_main(
        [
            "demo",
            "offline-job",
            "--backend",
            "postgresql",
            "--dsn",
            "postgresql+psycopg://user:secret@host/mind",
            "--episode-id",
            "episode-demo-offline",
        ]
    )

    assert exit_code == 0
    assert captured["admin_dsn"] == "postgresql+psycopg://user:secret@host/mind"
    assert captured["prefix"] == "mind_demo_offline_job"
    assert captured["migrated_dsn"] == "postgresql+psycopg://temp-demo-db"
    output = capsys.readouterr().out
    assert "backend=postgresql" in output
    assert "storage_scope=isolated" in output
    assert "job_kind=reflect_episode" in output
    assert "pending_job_count=1" in output


def test_gate_help_lists_real_gate_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["gate"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "phase-b" in output
    assert "phase-i" in output
    assert "phase-j" in output
    assert "phase-k" in output
    assert "product-readiness" in output
    assert "postgres-regression" in output


def test_gate_phase_b_dispatches_to_phase_b_main(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"count": 0}

    def fake_kernel_gate_main() -> int:
        called["count"] += 1
        return 17

    monkeypatch.setattr("mind.cli_demo_cmds.kernel_gate_main", fake_kernel_gate_main)

    exit_code = mind_main(["gate", "phase-b"])

    assert exit_code == 17
    assert called["count"] == 1


def test_gate_phase_i_forwards_output_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_access_gate_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("mind.cli_demo_cmds.access_gate_main", fake_access_gate_main)

    exit_code = mind_main(["gate", "phase-i", "--output", "/tmp/phase_i_gate.json"])

    assert exit_code == 0
    assert captured["argv"] == ["--output", "/tmp/phase_i_gate.json"]


def test_gate_phase_j_forwards_output_and_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_cli_gate_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("mind.cli_demo_cmds.cli_gate_main", fake_cli_gate_main)

    exit_code = mind_main(
        [
            "gate",
            "phase-j",
            "--output",
            "/tmp/phase_j_gate.json",
            "--dsn",
            "postgresql+psycopg://admin",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/phase_j_gate.json",
        "--dsn",
        "postgresql+psycopg://admin",
    ]


def test_gate_phase_k_forwards_output_and_live_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_capability_gate_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("mind.cli_demo_cmds.capability_gate_main", fake_capability_gate_main)

    exit_code = mind_main(
        [
            "gate",
            "phase-k",
            "--output",
            "/tmp/phase_k_gate.json",
            "--live-provider",
            "openai",
            "--live-provider",
            "claude",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/phase_k_gate.json",
        "--live-provider",
        "openai",
        "--live-provider",
        "claude",
    ]


def test_gate_product_readiness_forwards_output_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_product_readiness_gate_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_demo_cmds.product_readiness_gate_main",
        fake_product_readiness_gate_main,
    )

    exit_code = mind_main(
        [
            "gate",
            "product-readiness",
            "--output",
            "/tmp/product_readiness_gate.json",
            "--markdown-output",
            "/tmp/product_readiness_gate.md",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/product_readiness_gate.json",
        "--markdown-output",
        "/tmp/product_readiness_gate.md",
    ]


def test_gate_postgres_regression_forwards_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_postgres_regression_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_demo_cmds.postgres_regression_main",
        fake_postgres_regression_main,
    )

    exit_code = mind_main(
        ["gate", "postgres-regression", "--dsn", "postgresql+psycopg://example"],
    )

    assert exit_code == 0
    assert captured["argv"] == ["--dsn", "postgresql+psycopg://example"]


def test_report_help_lists_real_report_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["report"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "phase-f-ci" in output
    assert "phase-g-cost" in output
    assert "phase-k-compatibility" in output
    assert "product-transport" in output
    assert "deployment-smoke" in output
    assert "product-readiness" in output
    assert "acceptance" in output


def test_report_phase_f_ci_forwards_repeat_count_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_benchmark_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("mind.cli_ops_cmds.benchmark_report_main", fake_benchmark_report_main)

    exit_code = mind_main(
        [
            "report",
            "phase-f-ci",
            "--repeat-count",
            "5",
            "--output",
            "/tmp/phase_f_ci.json",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--repeat-count",
        "5",
        "--output",
        "/tmp/phase_f_ci.json",
    ]


def test_report_phase_g_cost_forwards_repeat_count_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_strategy_cost_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_ops_cmds.strategy_cost_report_main",
        fake_strategy_cost_report_main,
    )

    exit_code = mind_main(
        [
            "report",
            "phase-g-cost",
            "--repeat-count",
            "4",
            "--output",
            "/tmp/phase_g_cost.json",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--repeat-count",
        "4",
        "--output",
        "/tmp/phase_g_cost.json",
    ]


def test_report_phase_k_compatibility_forwards_output_and_live_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_capability_compatibility_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_ops_cmds.capability_compatibility_report_main",
        fake_capability_compatibility_report_main,
    )

    exit_code = mind_main(
        [
            "report",
            "phase-k-compatibility",
            "--output",
            "/tmp/phase_k_compatibility.json",
            "--live-provider",
            "gemini",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/phase_k_compatibility.json",
        "--live-provider",
        "gemini",
    ]


def test_report_product_transport_forwards_output_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_product_transport_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_ops_cmds.product_transport_report_main",
        fake_product_transport_report_main,
    )

    exit_code = mind_main(
        [
            "report",
            "product-transport",
            "--output",
            "/tmp/product_transport_audit.json",
            "--markdown-output",
            "/tmp/product_transport_audit.md",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/product_transport_audit.json",
        "--markdown-output",
        "/tmp/product_transport_audit.md",
    ]


def test_report_deployment_smoke_forwards_output_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_deployment_smoke_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_ops_cmds.deployment_smoke_report_main",
        fake_deployment_smoke_report_main,
    )

    exit_code = mind_main(
        [
            "report",
            "deployment-smoke",
            "--output",
            "/tmp/deployment_smoke_report.json",
            "--markdown-output",
            "/tmp/deployment_smoke_report.md",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/deployment_smoke_report.json",
        "--markdown-output",
        "/tmp/deployment_smoke_report.md",
    ]


def test_report_product_readiness_forwards_output_and_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_product_readiness_report_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(
        "mind.cli_ops_cmds.product_readiness_report_main",
        fake_product_readiness_report_main,
    )

    exit_code = mind_main(
        [
            "report",
            "product-readiness",
            "--output",
            "/tmp/product_readiness_report.json",
            "--markdown-output",
            "/tmp/product_readiness_report.md",
        ]
    )

    assert exit_code == 0
    assert captured["argv"] == [
        "--output",
        "/tmp/product_readiness_report.json",
        "--markdown-output",
        "/tmp/product_readiness_report.md",
    ]


def test_report_acceptance_prints_frozen_phase_report_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main(["report", "acceptance", "--phase", "h"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "phase=h" in output
    assert "docs/reports/phase_h_acceptance_report.md" in output
    assert "exists=true" in output


class _FakePostgresStore:
    def __init__(self) -> None:
        self.enqueued_jobs: list = []
        self.jobs: list[OfflineJob] = []
        self.raw_records: list[dict[str, str]] = []

    def __enter__(self) -> _FakePostgresStore:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def enqueue_offline_job(self, job: object) -> None:
        self.enqueued_jobs.append(job)

    def iter_offline_jobs(self, *, statuses: Sequence[OfflineJobStatus] = ()) -> list:
        if statuses:
            allowed = set(statuses)
            return [job for job in self.jobs if job.status in allowed]
        return list(self.jobs)

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, str]]:
        assert episode_id == "episode-777"
        return list(self.raw_records)


def test_offline_help_lists_real_offline_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["offline"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "worker" in output
    assert "list-jobs" in output
    assert "reflect-episode" in output
    assert "promote-schema" in output
    assert "replay" in output


def test_offline_worker_dispatches_to_worker_main(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Sequence[str] | None] = {"argv": None}

    def fake_offline_worker_main(argv: Sequence[str] | None = None) -> int:
        captured["argv"] = argv
        return 13

    monkeypatch.setattr("mind.cli_ops_cmds.offline_worker_main", fake_offline_worker_main)

    exit_code = mind_main(
        [
            "offline",
            "worker",
            "--dsn",
            "postgresql+psycopg://worker",
            "--max-jobs",
            "4",
            "--worker-id",
            "worker-x",
            "--job-kind",
            "reflect_episode",
            "--job-kind",
            "promote_schema",
        ]
    )

    assert exit_code == 13
    assert captured["argv"] == [
        "--dsn",
        "postgresql+psycopg://worker",
        "--max-jobs",
        "4",
        "--worker-id",
        "worker-x",
        "--job-kind",
        "reflect_episode",
        "--job-kind",
        "promote_schema",
    ]


def test_offline_list_jobs_prints_filtered_jobs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_store = _FakePostgresStore()
    fake_store.jobs = [
        new_offline_job(
            job_id="job-pending",
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(episode_id="episode-001"),
            now=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
        ),
        new_offline_job(
            job_id="job-succeeded",
            job_kind=OfflineJobKind.PROMOTE_SCHEMA,
            payload=PromoteSchemaJobPayload(
                target_refs=["obj-1", "obj-2"],
                reason="done",
            ),
            now=datetime(2026, 3, 10, 10, 1, tzinfo=UTC),
        ).model_copy(update={"status": OfflineJobStatus.SUCCEEDED}),
    ]

    monkeypatch.setattr("mind.cli_ops_cmds.PostgresMemoryStore", lambda dsn: fake_store)

    exit_code = mind_main(
        ["offline", "list-jobs", "--dsn", "postgresql+psycopg://jobs", "--status", "pending"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "job_count=1" in output
    assert "job-pending:reflect_episode:pending" in output


def test_offline_reflect_episode_enqueues_job(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakePostgresStore()
    monkeypatch.setattr("mind.cli_ops_cmds.PostgresMemoryStore", lambda dsn: fake_store)

    exit_code = mind_main(
        [
            "offline",
            "reflect-episode",
            "--dsn",
            "postgresql+psycopg://queue",
            "--episode-id",
            "episode-042",
            "--focus",
            "cli reflection",
            "--priority",
            "0.7",
            "--max-attempts",
            "5",
        ]
    )

    assert exit_code == 0
    assert len(fake_store.enqueued_jobs) == 1
    job = fake_store.enqueued_jobs[0]
    assert job.job_kind is OfflineJobKind.REFLECT_EPISODE
    assert job.payload["episode_id"] == "episode-042"
    assert job.payload["focus"] == "cli reflection"
    assert job.max_attempts == 5


def test_offline_promote_schema_enqueues_job(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakePostgresStore()
    monkeypatch.setattr("mind.cli_ops_cmds.PostgresMemoryStore", lambda dsn: fake_store)

    exit_code = mind_main(
        [
            "offline",
            "promote-schema",
            "--dsn",
            "postgresql+psycopg://queue",
            "--target-ref",
            "reflection-1",
            "--target-ref",
            "reflection-2",
            "--reason",
            "promote repeated pattern",
        ]
    )

    assert exit_code == 0
    assert len(fake_store.enqueued_jobs) == 1
    job = fake_store.enqueued_jobs[0]
    assert job.job_kind is OfflineJobKind.PROMOTE_SCHEMA
    assert job.payload["target_refs"] == ["reflection-1", "reflection-2"]


def test_offline_replay_ranks_candidate_ids(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_store = _FakePostgresStore()
    captured: dict[str, object] = {}

    def fake_select_replay_targets(
        store: object,
        candidate_ids: tuple[str, ...],
        *,
        top_k: int,
    ) -> tuple[ReplayTarget, ...]:
        captured["candidate_ids"] = candidate_ids
        captured["top_k"] = top_k
        return (ReplayTarget(object_id="candidate-b", score=1.25),)

    monkeypatch.setattr("mind.cli_ops_cmds.PostgresMemoryStore", lambda dsn: fake_store)
    monkeypatch.setattr("mind.cli_ops_cmds.select_replay_targets", fake_select_replay_targets)

    exit_code = mind_main(
        [
            "offline",
            "replay",
            "--dsn",
            "postgresql+psycopg://queue",
            "--candidate-id",
            "candidate-a",
            "--candidate-id",
            "candidate-b",
            "--top-k",
            "1",
        ]
    )

    assert exit_code == 0
    assert captured["candidate_ids"] == ("candidate-a", "candidate-b")
    assert captured["top_k"] == 1
    output = capsys.readouterr().out
    assert "candidate_source=explicit" in output
    assert "target_1=candidate-b:1.2500" in output


def test_offline_replay_can_derive_candidates_from_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store = _FakePostgresStore()
    fake_store.raw_records = [
        {"id": "episode-777-raw-01"},
        {"id": "episode-777-raw-02"},
    ]
    captured: dict[str, object] = {}

    def fake_select_replay_targets(
        store: object,
        candidate_ids: tuple[str, ...],
        *,
        top_k: int,
    ) -> tuple[ReplayTarget, ...]:
        captured["candidate_ids"] = candidate_ids
        captured["top_k"] = top_k
        return ()

    monkeypatch.setattr("mind.cli_ops_cmds.PostgresMemoryStore", lambda dsn: fake_store)
    monkeypatch.setattr("mind.cli_ops_cmds.select_replay_targets", fake_select_replay_targets)

    exit_code = mind_main(
        [
            "offline",
            "replay",
            "--dsn",
            "postgresql+psycopg://queue",
            "--episode-id",
            "episode-777",
        ]
    )

    assert exit_code == 0
    assert captured["candidate_ids"] == ("episode-777-raw-01", "episode-777-raw-02")
    assert captured["top_k"] == 2


def test_config_help_lists_real_config_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["config"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "show" in output
    assert "profile" in output
    assert "doctor" in output


def test_config_show_prints_default_sqlite_resolution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MIND_CLI_PROFILE", raising=False)
    monkeypatch.delenv("MIND_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("MIND_SQLITE_PATH", raising=False)

    exit_code = mind_main(["config", "show"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "requested_profile=auto" in output
    assert "resolved_profile=sqlite_local" in output
    assert "backend=sqlite" in output
    assert "sqlite_path=artifacts/dev/mind.sqlite3" in output


def test_config_show_cli_profile_override_beats_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MIND_CLI_PROFILE", "postgres_test")
    monkeypatch.setenv("MIND_POSTGRES_DSN", "postgresql+psycopg://user:secret@host/db")

    exit_code = mind_main(
        [
            "config",
            "show",
            "--profile",
            "postgres_main",
            "--dsn",
            "postgresql+psycopg://override:secret@host/main",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "requested_profile_source=cli" in output
    assert "resolved_profile=postgres_main" in output
    assert "postgres_dsn=postgresql+psycopg://override:***@host/main" in output


def test_config_profile_lists_frozen_catalog(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = mind_main(["config", "profile"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "profile_count=4" in output
    assert "auto:sqlite:none:" in output
    assert "postgres_main:postgresql:MIND_POSTGRES_DSN:" in output


def test_config_doctor_warns_when_postgres_dsn_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MIND_POSTGRES_DSN", raising=False)

    exit_code = mind_main(["config", "doctor", "--backend", "postgresql"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "overall_status=warn" in output
    assert "postgres_dsn:warn:missing:MIND_POSTGRES_DSN" in output


def test_primitive_help_lists_real_primitive_subcommands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = mind_main(["primitive"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "write-raw" in output
    assert "read" in output
    assert "retrieve" in output
    assert "summarize" in output
    assert "link" in output
    assert "reflect" in output
    assert "reorganize-simple" in output


def test_primitive_write_raw_and_read_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_primitive.sqlite3"

    write_exit = mind_main(
        [
            "primitive",
            "write-raw",
            "--sqlite-path",
            str(db_path),
            "--record-kind",
            "user_message",
            "--episode-id",
            "episode-cli-1",
            "--timestamp-order",
            "1",
            "--content",
            "remember the blue notebook",
        ]
    )

    assert write_exit == 0
    write_output = capsys.readouterr().out
    object_id = _extract_output_value(write_output, "object_id")
    assert _extract_output_value(write_output, "backend") == "sqlite"
    assert _extract_output_value(write_output, "provenance_id").startswith("prov-episode-cli-1")

    read_exit = mind_main(
        [
            "primitive",
            "read",
            "--sqlite-path",
            str(db_path),
            "--object-id",
            object_id,
        ]
    )

    assert read_exit == 0
    read_output = capsys.readouterr().out
    assert "object_count=1" in read_output
    assert f"object_1={object_id}:RawRecord:active" in read_output
    assert "remember the blue notebook" in read_output


def test_primitive_read_can_include_provenance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_primitive_provenance.sqlite3"

    write_exit = mind_main(
        [
            "primitive",
            "write-raw",
            "--sqlite-path",
            str(db_path),
            "--record-kind",
            "assistant_message",
            "--episode-id",
            "episode-cli-2",
            "--timestamp-order",
            "1",
            "--content",
            "assistant remembers provenance",
            "--provenance-json",
            (
                '{"producer_kind":"user","producer_id":"cli-user","captured_at":"2026-03-10T12:00:00Z",'
                '"source_channel":"chat","tenant_id":"tenant-a","user_id":"user-a",'
                '"ip_addr":"10.0.0.1","episode_id":"episode-cli-2"}'
            ),
        ]
    )

    assert write_exit == 0
    object_id = _extract_output_value(capsys.readouterr().out, "object_id")

    read_exit = mind_main(
        [
            "primitive",
            "read",
            "--sqlite-path",
            str(db_path),
            "--object-id",
            object_id,
            "--include-provenance",
        ]
    )

    assert read_exit == 0
    output = capsys.readouterr().out
    assert "provenance_summary_count=1" in output
    assert '"user_id":"user-a"' in output
    assert "ip_addr" not in output


def test_primitive_retrieve_returns_ranked_candidates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_primitive_retrieve.sqlite3"

    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "episode-cli-3",
                "--timestamp-order",
                "1",
                "--content",
                "alpha memory anchor",
            ]
        )
        == 0
    )
    first_output = capsys.readouterr().out
    alpha_object_id = _extract_output_value(first_output, "object_id")

    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "episode-cli-3",
                "--timestamp-order",
                "2",
                "--content",
                "beta unrelated note",
            ]
        )
        == 0
    )
    capsys.readouterr()

    retrieve_exit = mind_main(
        [
            "primitive",
            "retrieve",
            "--sqlite-path",
            str(db_path),
            "--query",
            "alpha",
        ]
    )

    assert retrieve_exit == 0
    output = capsys.readouterr().out
    assert "candidate_count=2" in output
    assert f"candidate_1={alpha_object_id}:" in output
    assert '"retrieval_backend":"store_search"' in output


def test_primitive_summarize_creates_summary_note(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_primitive_summary.sqlite3"

    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "user_message",
                "--episode-id",
                "episode-cli-4",
                "--timestamp-order",
                "1",
                "--content",
                "first summary ingredient",
            ]
        )
        == 0
    )
    first_id = _extract_output_value(capsys.readouterr().out, "object_id")
    assert (
        mind_main(
            [
                "primitive",
                "write-raw",
                "--sqlite-path",
                str(db_path),
                "--record-kind",
                "assistant_message",
                "--episode-id",
                "episode-cli-4",
                "--timestamp-order",
                "2",
                "--content",
                "second summary ingredient",
            ]
        )
        == 0
    )
    second_id = _extract_output_value(capsys.readouterr().out, "object_id")

    summarize_exit = mind_main(
        [
            "primitive",
            "summarize",
            "--sqlite-path",
            str(db_path),
            "--input-ref",
            first_id,
            "--input-ref",
            second_id,
            "--summary-scope",
            "episode",
            "--target-kind",
            "conversation_summary",
        ]
    )

    assert summarize_exit == 0
    summarize_output = capsys.readouterr().out
    summary_id = _extract_output_value(summarize_output, "summary_object_id")
    assert summary_id.startswith("summary-")

    read_exit = mind_main(
        [
            "primitive",
            "read",
            "--sqlite-path",
            str(db_path),
            "--object-id",
            summary_id,
        ]
    )

    assert read_exit == 0
    read_output = capsys.readouterr().out
    assert f"object_1={summary_id}:SummaryNote:active" in read_output
    assert '"target_kind":"conversation_summary"' in read_output


def test_primitive_reflect_requires_seeded_episode_and_raws(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "mind_cli_primitive_reflect.sqlite3"
    _seed_task_episode(db_path, episode_id="episode-cli-5", success=True)

    for timestamp_order, content in ((1, "first reflection raw"), (2, "second reflection raw")):
        assert (
            mind_main(
                [
                    "primitive",
                    "write-raw",
                    "--sqlite-path",
                    str(db_path),
                    "--record-kind",
                    "user_message",
                    "--episode-id",
                    "episode-cli-5",
                    "--timestamp-order",
                    str(timestamp_order),
                    "--content",
                    content,
                ]
            )
            == 0
        )
        capsys.readouterr()

    reflect_exit = mind_main(
        [
            "primitive",
            "reflect",
            "--sqlite-path",
            str(db_path),
            "--episode-id",
            "episode-cli-5",
            "--focus",
            "cli reflection focus",
        ]
    )

    assert reflect_exit == 0
    output = capsys.readouterr().out
    assert "reflection_object_id=reflection-" in output


def test_primitive_write_raw_can_use_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    class _FakePostgresStore:
        def __enter__(self) -> _FakePostgresStore:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    class _FakePrimitiveService:
        def __init__(self, store: object, **kwargs: object) -> None:
            captured["store"] = store

        def write_raw(self, request: object, context: object) -> PrimitiveExecutionResult:
            captured["request"] = request
            captured["context"] = context
            return PrimitiveExecutionResult(
                primitive=PrimitiveName.WRITE_RAW,
                outcome=PrimitiveOutcome.SUCCESS,
                response={
                    "object_id": "raw-postgres-1",
                    "version": 1,
                    "provenance_id": "prov-postgres-1",
                },
                target_ids=["raw-postgres-1"],
            )

    def fake_run_postgres_migrations(dsn: str) -> None:
        captured["migrated_dsn"] = dsn

    def fake_postgres_store(dsn: str) -> _FakePostgresStore:
        captured["store_dsn"] = dsn
        return _FakePostgresStore()

    monkeypatch.setattr("mind.cli.run_postgres_migrations", fake_run_postgres_migrations)
    monkeypatch.setattr("mind.cli.PostgresMemoryStore", fake_postgres_store)
    monkeypatch.setattr("mind.cli.PrimitiveService", _FakePrimitiveService)

    exit_code = mind_main(
        [
            "primitive",
            "write-raw",
            "--backend",
            "postgresql",
            "--dsn",
            "postgresql+psycopg://user:secret@host/mind",
            "--record-kind",
            "user_message",
            "--episode-id",
            "episode-cli-pg",
            "--timestamp-order",
            "1",
            "--content",
            "postgres primitive write",
        ]
    )

    assert exit_code == 0
    assert captured["migrated_dsn"] == "postgresql+psycopg://user:secret@host/mind"
    assert captured["store_dsn"] == "postgresql+psycopg://user:secret@host/mind"
    output = capsys.readouterr().out
    assert "backend=postgresql" in output
    assert "postgres_dsn=postgresql+psycopg://user:***@host/mind" in output
