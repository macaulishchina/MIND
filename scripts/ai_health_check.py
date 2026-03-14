"""AI governance health check for the MIND project.

Scans the codebase for quality metrics and produces a health report.
Run: uv run python scripts/ai_health_check.py [--output-dir .ai/health]
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(".ai/health")

REQUIRED_AI_FILES = [
    ".ai/CONSTITUTION.md",
    ".ai/ARCHITECTURE.md",
    ".ai/CONVENTIONS.md",
    ".ai/CURRENT_STATE.md",
    ".ai/CHANGE_PROTOCOL.md",
    ".ai/rules/kernel.md",
    ".ai/rules/primitives.md",
    ".ai/rules/app-services.md",
    ".ai/rules/api.md",
    ".ai/rules/testing.md",
    ".ai/rules/migration.md",
    ".ai/rules/docs.md",
    ".ai/checklists/new-service.md",
    ".ai/checklists/new-endpoint.md",
    ".ai/checklists/new-primitive.md",
    ".ai/checklists/bug-fix.md",
    ".ai/checklists/refactor.md",
    ".ai/health/drift-log.md",
]


def _run_command(cmd: list[str], *, timeout: int = 120) -> tuple[int, str]:
    """Run a command and return (exit_code, combined_output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return -2, f"Command not found: {cmd[0]}"


def check_ruff() -> dict[str, object]:
    """Run ruff check and count violations."""
    code, output = _run_command(
        ["uv", "run", "ruff", "check", "mind/", "tests/", "scripts/", "--output-format=json"],
    )
    violation_count = 0
    if code != 0:
        try:
            violations = json.loads(output)
            if isinstance(violations, list):
                violation_count = len(violations)
        except (json.JSONDecodeError, TypeError):
            # Count lines as fallback
            violation_count = len([ln for ln in output.strip().splitlines() if ln.strip()])

    return {
        "tool": "ruff",
        "passed": code == 0,
        "violation_count": violation_count,
    }


def check_mypy() -> dict[str, object]:
    """Run mypy and count errors."""
    code, output = _run_command(
        ["uv", "run", "mypy", "mind/", "tests/", "scripts/"],
        timeout=180,
    )
    error_count = 0
    if code != 0:
        for line in output.splitlines():
            if ": error:" in line:
                error_count += 1

    return {
        "tool": "mypy",
        "passed": code == 0,
        "error_count": error_count,
    }


def check_tests() -> dict[str, object]:
    """Run pytest and capture results."""
    code, output = _run_command(
        ["uv", "run", "pytest", "tests/", "-x", "--tb=line", "-q"],
        timeout=300,
    )
    # Parse pytest summary line like "93 passed", "5 failed, 88 passed"
    passed = 0
    failed = 0
    for line in output.splitlines():
        if "passed" in line or "failed" in line:
            parts = line.strip().split()
            for i, part in enumerate(parts):
                if part == "passed" or part == "passed,":
                    try:
                        passed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                if part == "failed" or part == "failed,":
                    try:
                        failed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass

    return {
        "tool": "pytest",
        "passed": code == 0,
        "tests_passed": passed,
        "tests_failed": failed,
    }


def check_ai_files() -> dict[str, object]:
    """Verify all required .ai/ files exist."""
    missing = [f for f in REQUIRED_AI_FILES if not Path(f).exists()]
    return {
        "check": "ai_files_integrity",
        "passed": len(missing) == 0,
        "total_required": len(REQUIRED_AI_FILES),
        "missing_count": len(missing),
        "missing_files": missing,
    }


def check_constitution_size() -> dict[str, object]:
    """Check CONSTITUTION.md stays under 500 lines."""
    path = Path(".ai/CONSTITUTION.md")
    if not path.exists():
        return {"check": "constitution_size", "passed": False, "lines": 0, "limit": 500}
    lines = len(path.read_text().splitlines())
    return {
        "check": "constitution_size",
        "passed": lines <= 500,
        "lines": lines,
        "limit": 500,
    }


def generate_report(output_dir: Path) -> dict[str, object]:
    """Generate a comprehensive health report."""
    print("🔍 Running AI governance health check...\n")

    results: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0.0",
        "checks": {},
    }

    # Run all checks
    checks = [
        ("ruff", check_ruff),
        ("mypy", check_mypy),
        ("pytest", check_tests),
        ("ai_files", check_ai_files),
        ("constitution_size", check_constitution_size),
    ]

    all_passed = True
    for name, check_fn in checks:
        print(f"  Running {name}...")
        result = check_fn()
        results["checks"][name] = result  # type: ignore[index]
        passed = result.get("passed", False)
        if not passed:
            all_passed = False
        status = "✅" if passed else "❌"
        print(f"  {status} {name}: {result}")

    results["all_passed"] = all_passed

    # Write report
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "latest-report.json"
    report_path.write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(f"\n📄 Report written to {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL CHECKS PASSED — project health is good.")
    else:
        print("❌ SOME CHECKS FAILED — review the report above.")
    print("=" * 60)

    return results


def main() -> None:
    """Entry point."""
    output_dir = DEFAULT_OUTPUT_DIR

    # Simple arg parsing
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--output-dir" and i + 1 < len(args):
            output_dir = Path(args[i + 1])

    report = generate_report(output_dir)
    if not report.get("all_passed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
