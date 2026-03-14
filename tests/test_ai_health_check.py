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


def test_build_pytest_command_uses_quick_parallel_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_check.os, "cpu_count", lambda: 2)

    command = health_check.build_pytest_command(full=False)

    assert command[:6] == ["uv", "run", "pytest", "tests/", "--tb=short", "-q"]
    assert "-m" in command
    assert "not slow and not gate" in command
    assert "-n" in command
    assert command[command.index("-n") + 1] == "4"
    assert "--dist" in command
    assert command[command.index("--dist") + 1] == "loadfile"


def test_build_pytest_command_full_omits_quick_only_args() -> None:
    command = health_check.build_pytest_command(full=True)

    assert "-m" not in command
    assert "-n" not in command
    assert "--dist" not in command


def test_parse_cli_args_defaults_to_quick(tmp_path: Path) -> None:
    output_dir, report_for_ai, compare_only, full = health_check._parse_cli_args(
        ["--output-dir", str(tmp_path), "--report-for-ai"]
    )

    assert output_dir == tmp_path
    assert report_for_ai is True
    assert compare_only is False
    assert full is False


def test_parse_cli_args_supports_full_and_quick_aliases(tmp_path: Path) -> None:
    output_dir, report_for_ai, compare_only, full = health_check._parse_cli_args(
        ["--output-dir", str(tmp_path), "--full", "--report-for-ai"]
    )

    assert output_dir == tmp_path
    assert report_for_ai is True
    assert compare_only is False
    assert full is True

    _, _, _, quick_full = health_check._parse_cli_args(["--full", "--quick"])
    assert quick_full is False


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
    assert result["tests_passed"] == 3
    assert result["tests_skipped"] == 1
    assert result["timing_available"] is True
    assert result["timing_path"] == str(tmp_path / "pytest-timing-latest.json")
    assert result["phase_summaries"][0]["phase"] == "j"
    assert result["slowest_tests"][0]["nodeid"] == "tests/test_phase_j_demo.py::test_demo"
    assert captured["timeout"] == health_check.PYTEST_RUN_TIMEOUT_SECONDS
    env = captured["env"]
    cmd = captured["cmd"]
    assert isinstance(env, dict)
    assert isinstance(cmd, list)
    assert env["MIND_PYTEST_TIMING_PATH"] == str(tmp_path / "pytest-timing-latest.json")
    assert "-n" in cmd


def test_generate_ai_repair_prompt_mentions_full_recheck() -> None:
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
