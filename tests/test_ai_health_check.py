from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_health_check_module() -> ModuleType:
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "ai_health_check.py"
    spec = importlib.util.spec_from_file_location("test_ai_health_check_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


health_check = _load_health_check_module()


def test_pytest_worker_count_uses_cpu_count_with_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_check.os, "cpu_count", lambda: 2)
    assert health_check._pytest_worker_count() == 4

    monkeypatch.setattr(health_check.os, "cpu_count", lambda: 6)
    assert health_check._pytest_worker_count() == 6


def test_build_pytest_command_uses_quick_parallel_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_check.os, "cpu_count", lambda: 2)

    command = health_check.build_pytest_command(full=False)

    assert command[:4] == ["uv", "run", "pytest", "tests/"]
    assert "--tb=short" in command
    assert "-q" in command
    assert "--ignore=tests/test_ai_health_check.py" in command
    assert "-m" in command
    assert "not slow and not gate" in command
    assert "-n" in command
    assert command[command.index("-n") + 1] == str(health_check._pytest_worker_count())
    assert "--dist" in command
    assert command[command.index("--dist") + 1] == "loadfile"


def test_build_pytest_command_full_omits_quick_only_args() -> None:
    command = health_check.build_pytest_command(full=True)

    assert "-m" not in command
    assert "--ignore=tests/test_ai_health_check.py" in command
    assert "-n" in command
    assert "--dist" in command


def test_build_pytest_command_serial_disables_parallel_args() -> None:
    command = health_check.build_pytest_command(full=True, serial=True)

    assert "-m" not in command
    assert "--ignore=tests/test_ai_health_check.py" in command
    assert "-n" not in command
    assert "--dist" not in command


def test_parse_cli_args_defaults_to_quick(tmp_path: Path) -> None:
    output_dir, report_for_ai, compare_only, full, serial = health_check._parse_cli_args(
        ["--output-dir", str(tmp_path), "--report-for-ai"]
    )

    assert output_dir == tmp_path
    assert report_for_ai is True
    assert compare_only is False
    assert full is False
    assert serial is False


def test_parse_cli_args_supports_full_and_quick_aliases(tmp_path: Path) -> None:
    output_dir, report_for_ai, compare_only, full, serial = health_check._parse_cli_args(
        ["--output-dir", str(tmp_path), "--full", "--report-for-ai"]
    )

    assert output_dir == tmp_path
    assert report_for_ai is True
    assert compare_only is False
    assert full is True
    assert serial is False

    _, _, _, quick_full, _ = health_check._parse_cli_args(["--full", "--quick"])
    assert quick_full is False


def test_parse_cli_args_supports_serial_override() -> None:
    _, _, _, full, serial = health_check._parse_cli_args(["--full", "--serial"])

    assert full is True
    assert serial is True

    _, _, _, _, parallel_serial = health_check._parse_cli_args(["--serial", "--parallel"])
    assert parallel_serial is False


def test_check_tests_injects_timing_path_and_reads_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str],
        *,
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        captured["env"] = env
        timing_path = Path((env or {})["MIND_PYTEST_TIMING_PATH"])
        timing_path.write_text(
            json.dumps(
                {
                    "generated_at": "2026-03-14T00:00:00+00:00",
                    "worker_count": 6,
                    "xdist_enabled": True,
                    "scheduler_mode": "loadfile(weighted)",
                    "totals": {
                        "test_case_count": 3,
                        "passed": 3,
                        "failed": 0,
                        "skipped": 1,
                        "total_duration_seconds": 1.25,
                    },
                    "phase_summaries": [
                        {
                            "phase": "j",
                            "test_case_count": 1,
                            "passed": 1,
                            "failed": 0,
                            "skipped": 0,
                            "total_duration_seconds": 0.5,
                        }
                    ],
                    "test_cases": [
                        {
                            "nodeid": "tests/test_phase_j_demo.py::test_demo",
                            "phase": "j",
                            "duration_seconds": 0.5,
                            "outcome": "passed",
                            "worker_id": "gw0",
                        }
                    ],
                }
            )
            + "\n"
        )
        return 0, "3 passed, 1 skipped in 0.12s\n", ""

    monkeypatch.setattr(health_check.os, "cpu_count", lambda: 6)
    monkeypatch.setattr(health_check, "_run", fake_run)

    result = health_check.check_tests(tmp_path, full=False)

    assert result["passed"] is True
    assert result["execution_mode"] == "quick"
    assert result["concurrency_mode"] == "parallel"
    assert result["tests_passed"] == 3
    assert result["tests_skipped"] == 1
    assert result["timing_available"] is True
    assert result["timing_path"] == str(tmp_path / "pytest-timing-latest.json")
    assert result["scheduler_mode"] == "loadfile(weighted)"
    assert result["phase_summaries"][0]["phase"] == "j"
    assert result["slowest_tests"][0]["nodeid"] == "tests/test_phase_j_demo.py::test_demo"
    assert captured["timeout"] == health_check.PYTEST_RUN_TIMEOUT_SECONDS
    env = captured["env"]
    cmd = captured["cmd"]
    assert isinstance(env, dict)
    assert isinstance(cmd, list)
    assert env["MIND_PYTEST_TIMING_PATH"] == str(tmp_path / "pytest-timing-latest.json")
    assert "-n" in cmd


def test_check_tests_serial_omits_parallel_pytest_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str],
        *,
        timeout: int = 120,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        captured["cmd"] = cmd
        timing_path = Path((env or {})["MIND_PYTEST_TIMING_PATH"])
        timing_path.write_text(json.dumps({"totals": {}, "test_cases": []}) + "\n")
        return 0, "1 passed in 0.01s\n", ""

    monkeypatch.setattr(health_check, "_run", fake_run)

    result = health_check.check_tests(tmp_path, full=True, serial=True)

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert result["execution_mode"] == "full"
    assert result["concurrency_mode"] == "serial"
    assert "-n" not in cmd
    assert "--dist" not in cmd


def test_generate_ai_repair_prompt_prefers_full_for_final_verification() -> None:
    prompt = health_check.generate_ai_repair_prompt(
        {
            "score": {"total": 90.0},
            "checks": {
                "pytest": {
                    "violations": [
                        {
                            "file": "tests/test_demo.py",
                            "line": 1,
                            "rule": "pytest/failed",
                            "message": "tests/test_demo.py::test_demo",
                            "fix_hint": "Fix the failing test.",
                        }
                    ]
                }
            },
            "drift": {"available": False},
        }
    )

    assert "--report-for-ai" in prompt
    assert "--full --report-for-ai" in prompt
    assert "intermediate feedback" in prompt
    assert "instead of" in prompt


def test_pytest_progress_bar_reports_worker_summary_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 100.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=4)

    bar.update("gw0", "PASSED")
    now["value"] = 101.0
    bar.update("gw0", "FAILED")
    now["value"] = 102.0
    bar.update("gw1", "PASSED")
    now["value"] = 105.0

    lines = bar._build_lines()

    assert (
        lines[0]
        == "  🧵 workers │ total 4  active 2  idle 2  avg 0.8/w  "
        "max gw0:2  min gw2:0  imbalance 2.67x"
    )
    assert lines[1].startswith("  ⏳ [")
    assert "   30%  3/10  ✅2 ❌1 ⏭0  ⏱ total 5s" in lines[1]
    assert lines[2] == "  📦 workers │"
    assert lines[3].startswith("          │ \x1b[31mgw0:  2 [")
    assert "  67%  " in lines[3]
    assert lines[3].endswith("\x1b[0m")
    assert lines[4].startswith("          │ gw1:  1 [")
    assert "  33%  " in lines[4]
    assert lines[5].startswith("          │ gw2:  0 [")
    assert "   0%  waiting" in lines[5]
    assert lines[6].startswith("          │ gw3:  0 [")
    assert "   0%  waiting" in lines[6]


def test_pytest_progress_bar_shows_collecting_state_before_results() -> None:
    bar = health_check._PytestProgressBar(total=5, worker_count=3)

    lines = bar._build_lines()

    assert lines[0] == "  🧵 workers │ total 3  active 0  idle 3  avg 0.0/w  collecting..."


def test_pytest_progress_bar_shows_single_worker_summary_for_full_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 50.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=5, worker_count=1)

    bar.update("main", "PASSED")
    now["value"] = 51.0
    lines = bar._build_lines()

    assert (
        lines[0]
        == "  🧵 workers │ total 1  active 1  idle 0  avg 1.0/w  "
        "max main:1  min main:1  imbalance 1.00x"
    )
    assert lines[1].startswith("  ⏳ [")
    assert "   20%  1/5  ✅1 ❌0 ⏭0  ⏱ total 1s" in lines[1]
    assert lines[2] == "  📦 workers │"
    assert lines[3].startswith("          │ main:  1 [")
    assert " 100%  running     1s" in lines[3]


def test_pytest_progress_bar_aligns_worker_bars_for_different_count_widths() -> None:
    bar = health_check._PytestProgressBar(total=200, worker_count=4)
    bar.workers = {
        "gw0": {"done": 14, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
        "gw1": {"done": 77, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
        "gw2": {"done": 9, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
        "gw3": {"done": 114, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
    }
    bar.completed = 214

    cells = [bar._format_worker_cell(worker_id) for worker_id in ("gw0", "gw1", "gw2", "gw3")]
    bar_columns = [cell.index("[") for cell in cells]

    assert bar_columns == [bar_columns[0]] * len(bar_columns)


def test_pytest_progress_bar_worker_bar_scales_to_busiest_worker() -> None:
    bar = health_check._PytestProgressBar(total=100, worker_count=2)
    bar.completed = 100
    bar.workers = {
        "gw0": {"done": 10, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
        "gw1": {"done": 40, "fail": 0, "first_seen": 1.0, "last_update": 1.0},
    }

    cell_small = bar._format_worker_cell("gw0")
    cell_large = bar._format_worker_cell("gw1")

    assert "[██████" in cell_small
    assert cell_small.count("█") == 6
    assert "  10%" in cell_small
    assert "[████████████████████████]" in cell_large
    assert cell_large.count("█") == 24
    assert "  40%" in cell_large


def test_pytest_progress_bar_shows_current_test_for_running_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_example", worker_id="gw0")
    line = bar._format_worker_cell("gw0")

    assert "running" in line
    assert "test_demo.py::test_example" in line


def test_pytest_progress_bar_completion_rebinds_current_test_to_worker() -> None:
    bar = health_check._PytestProgressBar(total=10, worker_count=2)
    bar.note_test_start("tests/test_demo.py::test_example", worker_id="gw0")

    bar.bind_completed_test("gw1", "tests/test_demo.py::test_example")

    assert bar._worker_current_test("gw0") == "tests/test_demo.py::test_example"
    assert bar._worker_current_test("gw1") == ""


def test_pytest_progress_bar_summary_counts_running_workers_without_results() -> None:
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_example", worker_id="gw0")
    summary = bar._build_worker_summary_line()

    assert "active 1" in summary
    assert "idle 1" in summary


def test_pytest_progress_bar_parallel_mode_tracks_longest_observed_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_example")
    now["value"] = 13.0
    lines = bar._build_lines()

    assert lines[2] == "  📝 longest observed │ test_demo.py::test_example  3s"
    assert "running" not in bar._format_worker_cell("gw0")


def test_pytest_progress_bar_completed_test_remains_longest_observed_until_beaten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_old")
    now["value"] = 15.0
    bar.bind_completed_test("gw0", "tests/test_demo.py::test_old")

    now["value"] = 16.0
    bar.note_test_start("tests/test_demo.py::test_new")
    lines = bar._build_lines()

    assert lines[2] == "  📝 longest observed │ test_demo.py::test_old  5s"


def test_pytest_progress_bar_completed_test_with_trailing_space_updates_longest_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_old")
    now["value"] = 14.0
    bar.bind_completed_test("gw0", "tests/test_demo.py::test_old ")

    now["value"] = 15.0
    bar.note_test_start("tests/test_demo.py::test_new")
    lines = bar._build_lines()

    assert lines[2] == "  📝 longest observed │ test_demo.py::test_old  4s"


def test_pytest_progress_bar_longer_active_case_replaces_previous_longest_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=2)

    bar.note_test_start("tests/test_demo.py::test_old")
    now["value"] = 14.0
    bar.bind_completed_test("gw0", "tests/test_demo.py::test_old")

    now["value"] = 15.0
    bar.note_test_start("tests/test_demo.py::test_new")
    now["value"] = 21.0
    lines = bar._build_lines()

    assert lines[2] == "  📝 longest observed │ test_demo.py::test_new  6s"


def test_pytest_progress_bar_does_not_round_incomplete_run_to_100_percent() -> None:
    bar = health_check._PytestProgressBar(total=1056, worker_count=1)
    bar.completed = 1055

    lines = bar._build_lines()

    assert "100%" not in lines[1]
    assert " 99%" in lines[1]


def test_pytest_progress_bar_shows_full_current_test_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 10.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=1)

    bar.note_test_start(
        "tests/test_phase_k_capability_service.py::"
        "test_build_capability_adapters_from_environment_returns_correctly_"
        "configured_provider",
        worker_id="main",
    )
    line = bar._format_worker_cell("main")

    assert "configured_provider" in line
    assert "…" not in line


def test_pytest_progress_bar_running_worker_with_done_count_keeps_current_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"value": 20.0}
    monkeypatch.setattr(health_check.time, "monotonic", lambda: now["value"])
    bar = health_check._PytestProgressBar(total=10, worker_count=1)
    bar.workers = {
        "main": {
            "done": 3,
            "fail": 0,
            "first_seen": 10.0,
            "last_update": 11.0,
            "current_test": "tests/test_demo.py::test_still_running",
        }
    }

    line = bar._format_worker_cell("main")

    assert "running" in line
    assert "test_demo.py::test_still_running" in line


def test_pytest_progress_bar_finalizing_status_overrides_running() -> None:
    bar = health_check._PytestProgressBar(total=10, worker_count=1)
    bar.workers = {
        "main": {
            "done": 10,
            "fail": 0,
            "first_seen": 10.0,
            "last_update": 10.0,
            "current_test": "tests/test_demo.py::test_done",
        }
    }

    bar.set_finalizing(True)
    line = bar._format_worker_cell("main")

    assert "teardown" in line
