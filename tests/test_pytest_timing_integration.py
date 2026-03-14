from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_pytest_timing_report_writes_json_and_terminal_summary(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    timing_path = tmp_path / "pytest-timing.json"
    env = os.environ.copy()
    env["MIND_PYTEST_TIMING_PATH"] = str(timing_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_pytest_timing_probe.py",
            "tests/test_phase_j_timing_probe.py",
            "-q",
            "--no-header",
        ],
        capture_output=True,
        cwd=repo_root,
        env=env,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(timing_path.read_text())
    phase_summaries = {summary["phase"]: summary for summary in payload["phase_summaries"]}

    assert payload["xdist_enabled"] is False
    assert payload["totals"]["test_case_count"] == 3
    assert phase_summaries["j"]["test_case_count"] == 1
    assert phase_summaries["j"]["passed"] == 1
    assert phase_summaries["unphased"]["test_case_count"] == 2

    phases = {summary["phase"] for summary in payload["phase_summaries"]}
    nodeids = {case["nodeid"] for case in payload["test_cases"]}
    combined_output = result.stdout + result.stderr

    assert phases == {"j", "unphased"}
    assert "tests/test_phase_j_timing_probe.py::test_phase_j_timing_probe_case" in nodeids
    assert "tests/test_pytest_timing_probe.py::test_timing_probe_slow_case" in nodeids
    assert "Pytest timing summary" in combined_output
    assert "Phase j:" in combined_output
    assert "Slow test:" in combined_output
