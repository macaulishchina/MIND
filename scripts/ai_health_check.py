"""AI governance health check for the MIND project.

Comprehensive health scanner that verifies code quality, architecture
invariants, and .ai/ governance compliance.  Produces structured reports
that an AI agent can consume to self-diagnose and self-repair.

Usage:
    uv run python scripts/ai_health_check.py                 # full scan
    uv run python scripts/ai_health_check.py --report-for-ai # emit AI repair prompt
    uv run python scripts/ai_health_check.py --compare       # diff latest vs baseline
    uv run python scripts/ai_health_check.py --output-dir .ai/health
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = Path(".ai/health")
MAX_HISTORY = 20  # keep last N reports in history ring-buffer

SCAN_DIRS = ["mind/", "tests/", "scripts/"]

REQUIRED_AI_FILES = [
    ".ai/CONSTITUTION.md",
    ".ai/ARCHITECTURE.md",
    ".ai/CONVENTIONS.md",
    ".ai/CURRENT_STATE.md",
    ".ai/CHANGE_PROTOCOL.md",
    ".ai/rules/app-core.md",
    ".ai/rules/kernel.md",
    ".ai/rules/primitives.md",
    ".ai/rules/domain-services.md",
    ".ai/rules/app-services.md",
    ".ai/rules/api.md",
    ".ai/rules/transport.md",
    ".ai/rules/telemetry.md",
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

REQUIRED_HUMAN_FILES = [
    ".human/README.md",
    ".human/角色转变.md",
    ".human/工作流程.md",
    ".human/工具链.md",
    ".human/注意事项.md",
    ".human/规则维护.md",
    ".human/自纠机制.md",
]

ROOT_AGENT_ENTRYPOINT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
PLANS_TEMPLATE_PATH = Path(".ai/templates/PLANS.md")
PLAN_TEMPLATE_REQUIRED_SECTIONS = (
    "# Execution Plan",
    "## Goal",
    "## Constraints",
    "## Steps",
    "## Verification",
    "## Progress Log",
)

# Architecture layer definition  (lower index = lower layer)
# §2.1: Upper layers call down only.
LAYER_ORDER: dict[str, int] = {
    "mind.kernel": 0,
    "mind.primitives": 1,
    "mind.access": 2,
    "mind.governance": 2,
    "mind.capabilities": 2,
    "mind.offline": 2,
    "mind.app": 3,
    "mind.mcp": 4,
    "mind.api": 4,
    "mind.frontend": 4,
}

# CLI modules are exempt from print() checks
CLI_MODULES = {
    "mind/cli.py",
    "mind/cli_demo_cmds.py",
    "mind/cli_gates.py",
    "mind/cli_ops_cmds.py",
    "mind/cli_output.py",
    "mind/cli_phase_gates.py",
    "mind/cli_primitive_cmds.py",
    "mind/devcli.py",
    "mind/cli_gate.py",
    "mind/product_cli.py",
}

FILE_LINE_LIMIT = 800
CONSTITUTION_LINE_LIMIT = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(
    cmd: list[str], *, timeout: int = 120
) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return -2, "", f"Command not found: {cmd[0]}"


def _py_files(dirs: list[str] | None = None) -> list[Path]:
    """Collect all .py files under the given dirs."""
    targets = dirs or ["mind/"]
    files: list[Path] = []
    for d in targets:
        p = Path(d)
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
    return files


def _module_for_path(path: Path) -> str:
    """Convert file path to dotted module prefix for layer lookup."""
    parts = path.parts
    if parts[0] != "mind":
        return ""
    # Return the first two parts: mind.kernel, mind.app, etc.
    if len(parts) >= 2:
        return f"mind.{parts[1].removesuffix('.py')}"
    return "mind"


def _layer_of(module: str) -> int | None:
    """Return the layer index for a module prefix, or None if unknown."""
    for prefix, level in LAYER_ORDER.items():
        if module == prefix or module.startswith(prefix + "."):
            return level
    return None


Violation = dict[str, Any]  # {file, line, rule, message, fix_hint}


def _v(
    file: str, line: int, rule: str, message: str, fix_hint: str = ""
) -> Violation:
    return {
        "file": file,
        "line": line,
        "rule": rule,
        "message": message,
        "fix_hint": fix_hint,
    }


# ---------------------------------------------------------------------------
# Check: ruff  (with per-rule-category breakdown)
# ---------------------------------------------------------------------------

def check_ruff() -> dict[str, Any]:
    """Run ruff check with JSON output, parse by rule category."""
    code, stdout, _stderr = _run(
        ["uv", "run", "ruff", "check", *SCAN_DIRS, "--output-format=json"],
    )
    violations: list[dict[str, Any]] = []
    by_category: Counter[str] = Counter()
    by_file: Counter[str] = Counter()
    items: list[Violation] = []

    if code != 0 and stdout.strip():
        try:
            violations = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            violations = []

    for v in violations:
        rule_code: str = v.get("code", "?")
        category = rule_code[0] if rule_code else "?"
        by_category[category] += 1
        fname = v.get("filename", "?")
        by_file[fname] += 1
        loc = v.get("location", {})
        items.append(_v(
            fname,
            loc.get("row", 0),
            f"ruff/{rule_code}",
            v.get("message", ""),
            fix_hint=f"Run: uv run ruff check --fix {fname}",
        ))

    return {
        "tool": "ruff",
        "passed": code == 0,
        "violation_count": len(violations),
        "by_category": dict(by_category.most_common()),
        "by_file_top10": dict(by_file.most_common(10)),
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: mypy  (with per-module breakdown)
# ---------------------------------------------------------------------------

def check_mypy() -> dict[str, Any]:
    """Run mypy on all targets, parse errors by module."""
    code, stdout, stderr = _run(
        ["uv", "run", "mypy", *SCAN_DIRS], timeout=180,
    )
    output = stdout + stderr
    by_module: Counter[str] = Counter()
    items: list[Violation] = []

    for line in output.splitlines():
        if ": error:" not in line:
            continue
        # Format: path/file.py:42: error: Some message  [error-code]
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        fpath = parts[0].strip()
        lineno = int(parts[1]) if parts[1].strip().isdigit() else 0
        msg = parts[3].strip().removeprefix("error:").strip()
        # Module bucket
        mod = fpath.replace("/", ".").removesuffix(".py")
        top = ".".join(mod.split(".")[:2]) if "." in mod else mod
        by_module[top] += 1
        items.append(_v(fpath, lineno, "mypy", msg))

    return {
        "tool": "mypy",
        "passed": code == 0,
        "error_count": len(items),
        "by_module": dict(by_module.most_common()),
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: pytest  (full run, no -x; capture errors/skipped/warnings)
# ---------------------------------------------------------------------------

def check_tests(*, quick: bool = False) -> dict[str, Any]:
    """Run pytest with per-test timeout and fail-fast."""
    cmd = [
        "uv", "run", "pytest", "tests/",
        "--tb=short", "-q", "--no-header",
        "--timeout=30", "-x",
    ]
    if quick:
        cmd.extend(["-m", "not slow and not gate"])
    code, stdout, stderr = _run(cmd, timeout=300)
    output = stdout + stderr
    passed = failed = errors = skipped = warnings = 0
    failed_tests: list[str] = []

    for line in output.splitlines():
        # Summary line: "37 passed, 1 failed, 2 warnings"
        if "passed" in line or "failed" in line or "error" in line:
            for token in re.findall(r"(\d+)\s+(passed|failed|error|skipped|warning)", line):
                count = int(token[0])
                kind = token[1]
                if kind == "passed":
                    passed = count
                elif kind == "failed":
                    failed = count
                elif kind == "error":
                    errors = count
                elif kind == "skipped":
                    skipped = count
                elif kind == "warning":
                    warnings = count
        # FAILED lines: "FAILED tests/test_foo.py::test_bar - AssertionError"
        if line.startswith("FAILED "):
            failed_tests.append(line.removeprefix("FAILED ").strip())

    items = [
        _v(
            ft.split("::")[0] if "::" in ft else ft,
            0,
            "pytest/failed",
            ft,
            fix_hint="Read the traceback above, fix the assertion or the code under test.",
        )
        for ft in failed_tests
    ]

    return {
        "tool": "pytest",
        "passed": code == 0,
        "tests_passed": passed,
        "tests_failed": failed,
        "tests_errors": errors,
        "tests_skipped": skipped,
        "tests_warnings": warnings,
        "failed_tests": failed_tests,
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: architecture layer violations  (§2.1 of CONSTITUTION)
# ---------------------------------------------------------------------------

def check_architecture() -> dict[str, Any]:
    """Detect upward imports that violate the layered architecture."""
    items: list[Violation] = []
    files = _py_files(["mind/"])

    for fpath in files:
        src_mod = _module_for_path(fpath)
        src_layer = _layer_of(src_mod)
        if src_layer is None:
            continue

        try:
            tree = ast.parse(fpath.read_text(), filename=str(fpath))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            target_mod: str | None = None
            if isinstance(node, ast.ImportFrom) and node.module:
                target_mod = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("mind."):
                        target_mod = alias.name
                        break
            if not target_mod or not target_mod.startswith("mind."):
                continue

            # Find the layer of the target
            target_top = ".".join(target_mod.split(".")[:2])
            tgt_layer = _layer_of(target_top)
            if tgt_layer is None:
                continue

            if tgt_layer > src_layer:
                items.append(_v(
                    str(fpath),
                    getattr(node, "lineno", 0),
                    "arch/upward-import",
                    f"{src_mod} (layer {src_layer}) imports {target_mod} (layer {tgt_layer})",
                    fix_hint=(
                        "Move the shared type to a lower layer, or invert the dependency. "
                        "See .ai/CONSTITUTION.md §2.1."
                    ),
                ))

    # Also check: API layer bypassing app services (§2.1)
    for fpath in _py_files(["mind/api/", "mind/mcp/"]):
        try:
            tree = ast.parse(fpath.read_text(), filename=str(fpath))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            target_mod = None
            if isinstance(node, ast.ImportFrom) and node.module:
                target_mod = node.module
            if not target_mod:
                continue
            if (
                target_mod.startswith("mind.primitives")
                or target_mod.startswith("mind.kernel")
            ):
                items.append(_v(
                    str(fpath),
                    getattr(node, "lineno", 0),
                    "arch/transport-bypasses-app",
                    f"Transport layer imports {target_mod} directly (must go through mind.app)",
                    fix_hint="Route through an app service. See .ai/CONSTITUTION.md §2.1.",
                ))

    return {
        "check": "architecture",
        "passed": len(items) == 0,
        "violation_count": len(items),
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: forbidden patterns  (§5 of CONSTITUTION)
# ---------------------------------------------------------------------------

def check_forbidden_patterns() -> dict[str, Any]:
    """Scan for patterns banned in CONSTITUTION §5."""
    items: list[Violation] = []
    files = _py_files(["mind/"])

    for fpath in files:
        fstr = str(fpath)
        try:
            source = fpath.read_text()
            lines = source.splitlines()
        except OSError:
            continue

        # --- File length > 800 lines ---
        if len(lines) > FILE_LINE_LIMIT:
            items.append(_v(
                fstr, len(lines), "forbidden/file-too-long",
                f"File has {len(lines)} lines (limit {FILE_LINE_LIMIT})",
                fix_hint="Split this module into smaller files.",
            ))

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # --- import * ---
            if re.match(r"from\s+\S+\s+import\s+\*", stripped):
                items.append(_v(
                    fstr, i, "forbidden/import-star",
                    f"Wildcard import: {stripped}",
                    fix_hint="Use explicit imports.",
                ))

            # --- bare except ---
            if re.match(r"except\s*:", stripped):
                items.append(_v(
                    fstr, i, "forbidden/bare-except",
                    "Bare except: clause",
                    fix_hint="Catch a specific exception type.",
                ))

            # --- except Exception: pass ---
            if re.match(r"except\s+Exception\s*:\s*pass", stripped):
                items.append(_v(
                    fstr, i, "forbidden/swallowed-exception",
                    "Exception swallowed with bare pass",
                    fix_hint="Log the exception or re-raise.",
                ))

            # --- TODO / FIXME / HACK / XXX markers in production code ---
            if re.search(r"#.*\b(TODO|FIXME|HACK|XXX)\b", line):
                items.append(_v(
                    fstr, i, "forbidden/placeholder-marker",
                    f"Placeholder marker in production code: {stripped}",
                    fix_hint="Resolve it or record the follow-up in a plan/drift log.",
                ))

            # --- raise NotImplementedError ---
            if re.search(r"raise\s+NotImplementedError(?:\(|\b)", stripped):
                items.append(_v(
                    fstr, i, "forbidden/not-implemented",
                    "raise NotImplementedError in production code",
                    fix_hint="Use an abstract base class or provide the final implementation.",
                ))

            # --- print() in non-CLI modules ---
            if fstr not in CLI_MODULES and re.match(r"print\s*\(", stripped):
                # Exclude comments and strings (rough heuristic)
                if not stripped.startswith("#"):
                    items.append(_v(
                        fstr, i, "forbidden/print-in-library",
                        "print() in library code (use logging)",
                        fix_hint="Replace with _log.info() or _log.debug().",
                    ))

            # --- # type: ignore without explanation ---
            if "# type: ignore" in line:
                # Acceptable: # type: ignore[code]  -- some reason
                if not re.search(r"#\s*type:\s*ignore\[.+\]", line):
                    items.append(_v(
                        fstr, i, "forbidden/untyped-ignore",
                        "# type: ignore without error code",
                        fix_hint="Add error code: # type: ignore[error-code]  -- reason",
                    ))

        # --- Mutable default arguments (AST check) ---
        try:
            tree = ast.parse(source, filename=fstr)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, ast.List | ast.Dict | ast.Set):
                        items.append(_v(
                            fstr,
                            default.lineno,
                            "forbidden/mutable-default",
                            "Mutable default argument in function signature",
                            fix_hint="Use None as default + create inside function body.",
                        ))

    return {
        "check": "forbidden_patterns",
        "passed": len(items) == 0,
        "violation_count": len(items),
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: governance file integrity  (.ai/ + .human/)
# ---------------------------------------------------------------------------

def check_governance_files() -> dict[str, Any]:
    """Verify all required .ai/ and .human/ files exist and are non-empty."""
    all_required = REQUIRED_AI_FILES + REQUIRED_HUMAN_FILES
    missing: list[str] = []
    empty: list[str] = []

    for f in all_required:
        p = Path(f)
        if not p.exists():
            missing.append(f)
        elif p.stat().st_size == 0:
            empty.append(f)

    items = [
        _v(f, 0, "governance/missing-file", f"Required file missing: {f}",
           fix_hint=f"Create {f} per .ai/CONSTITUTION.md")
        for f in missing
    ] + [
        _v(f, 0, "governance/empty-file", f"Required file is empty: {f}",
           fix_hint=f"Populate {f} with content")
        for f in empty
    ]

    # Constitution size
    const_path = Path(".ai/CONSTITUTION.md")
    const_lines = 0
    if const_path.exists():
        const_lines = len(const_path.read_text().splitlines())
        if const_lines > CONSTITUTION_LINE_LIMIT:
            items.append(_v(
                str(const_path), const_lines,
                "governance/constitution-too-large",
                f"CONSTITUTION.md has {const_lines} lines (limit {CONSTITUTION_LINE_LIMIT})",
                fix_hint="Refactor rules into .ai/rules/ files and reference them.",
            ))

    return {
        "check": "governance_files",
        "passed": len(items) == 0,
        "violation_count": len(items),
        "total_required": len(all_required),
        "missing_count": len(missing),
        "empty_count": len(empty),
        "constitution_lines": const_lines,
        "constitution_limit": CONSTITUTION_LINE_LIMIT,
        "missing_files": missing,
        "empty_files": empty,
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Check: agent assets  (repo-native instructions + plan template)
# ---------------------------------------------------------------------------

def check_agent_assets() -> dict[str, Any]:
    """Verify agent entrypoint files and plan template exist and stay useful."""
    items: list[Violation] = []
    present_files = [Path(name) for name in ROOT_AGENT_ENTRYPOINT_FILES if Path(name).exists()]
    entrypoint_texts: dict[str, str] = {}

    if not present_files:
        items.append(_v(
            ".",
            0,
            "agent/missing-entrypoint",
            "No root agent instruction file found (expected AGENTS.md, CLAUDE.md, or GEMINI.md).",
            fix_hint="Add a root agent instruction file that points to .ai/CONSTITUTION.md.",
        ))
    else:
        for path in present_files:
            text = path.read_text().strip()
            entrypoint_texts[str(path)] = text
            if not text:
                items.append(_v(
                    str(path),
                    0,
                    "agent/empty-entrypoint",
                    f"Agent instruction file is empty: {path}",
                    fix_hint=(
                        "Add a short repo-specific entrypoint that points to "
                        ".ai/CONSTITUTION.md."
                    ),
                ))

        if not any(".ai/CONSTITUTION.md" in text for text in entrypoint_texts.values()):
            items.append(_v(
                ".",
                0,
                "agent/missing-constitution-reference",
                "No root agent instruction file references .ai/CONSTITUTION.md.",
                fix_hint="Point at .ai/CONSTITUTION.md from AGENTS.md, CLAUDE.md, or GEMINI.md.",
            ))

        if not any(".ai/templates/PLANS.md" in text for text in entrypoint_texts.values()):
            items.append(_v(
                ".",
                0,
                "agent/missing-plan-reference",
                "No root agent instruction file references .ai/templates/PLANS.md.",
                fix_hint="Tell agents when to create PLANS.md from the template.",
            ))

    if not PLANS_TEMPLATE_PATH.exists():
        items.append(_v(
            str(PLANS_TEMPLATE_PATH),
            0,
            "agent/missing-plan-template",
            "Missing plan template: .ai/templates/PLANS.md",
            fix_hint="Add the execution plan template under .ai/templates/PLANS.md.",
        ))
    else:
        plan_text = PLANS_TEMPLATE_PATH.read_text().strip()
        if not plan_text:
            items.append(_v(
                str(PLANS_TEMPLATE_PATH),
                0,
                "agent/empty-plan-template",
                "Plan template exists but is empty.",
                fix_hint="Populate the plan template with required sections.",
            ))
        else:
            for heading in PLAN_TEMPLATE_REQUIRED_SECTIONS:
                if heading not in plan_text:
                    items.append(_v(
                        str(PLANS_TEMPLATE_PATH),
                        0,
                        "agent/plan-template-missing-section",
                        f"Plan template missing section: {heading}",
                        fix_hint="Add the missing heading to keep execution plans consistent.",
                    ))

    return {
        "check": "agent_assets",
        "passed": len(items) == 0,
        "violation_count": len(items),
        "entrypoint_count": len(present_files),
        "violations": items,
    }


# ---------------------------------------------------------------------------
# Scoring — quantify health as 0-100
# ---------------------------------------------------------------------------

def compute_score(checks: dict[str, Any]) -> dict[str, Any]:
    """Compute a weighted 0-100 health score from check results.

    Weights (total 100):
      ruff:           20  (each violation costs 0.1 pt, max deduction 20)
      mypy:           20  (each error costs 0.1 pt, max deduction 20)
      pytest:         30  (proportional to pass rate; 0 tests = 0 pts)
      architecture:   15  (each violation costs 3 pts, max deduction 15)
      governance:      5  (proportional to files present & constitution ok)
      agent_assets:    5  (repo-native instructions and plan template)
      forbidden:       5  (each violation costs 0.5 pt, max deduction 5)
    """
    scores: dict[str, float] = {}

    # ruff
    ruff = checks.get("ruff", {})
    ruff_v = ruff.get("violation_count", 0)
    scores["ruff"] = max(0.0, 20.0 - ruff_v * 0.1)

    # mypy
    mypy = checks.get("mypy", {})
    mypy_e = mypy.get("error_count", 0)
    scores["mypy"] = max(0.0, 20.0 - mypy_e * 0.1)

    # pytest
    pt = checks.get("pytest", {})
    total_tests = pt.get("tests_passed", 0) + pt.get("tests_failed", 0)
    if total_tests > 0:
        scores["pytest"] = 30.0 * pt.get("tests_passed", 0) / total_tests
    else:
        scores["pytest"] = 0.0

    # architecture
    arch = checks.get("architecture", {})
    arch_v = arch.get("violation_count", 0)
    scores["architecture"] = max(0.0, 15.0 - arch_v * 3.0)

    # governance
    gov = checks.get("governance_files", {})
    total_req = gov.get("total_required", 25)
    present = total_req - gov.get("missing_count", 0) - gov.get("empty_count", 0)
    gov_score = 5.0 * present / total_req if total_req > 0 else 0.0
    const_lines = gov.get("constitution_lines", 0)
    const_limit = gov.get("constitution_limit", CONSTITUTION_LINE_LIMIT)
    if const_lines > const_limit:
        gov_score = max(0.0, gov_score - 2.0)
    scores["governance"] = gov_score

    # agent assets
    agent = checks.get("agent_assets", {})
    agent_v = agent.get("violation_count", 0)
    scores["agent_assets"] = max(0.0, 5.0 - agent_v * 1.0)

    # forbidden patterns
    fp = checks.get("forbidden_patterns", {})
    fp_v = fp.get("violation_count", 0)
    scores["forbidden"] = max(0.0, 5.0 - fp_v * 0.5)

    total = sum(scores.values())
    return {"total": round(total, 1), "breakdown": {k: round(v, 1) for k, v in scores.items()}}


# ---------------------------------------------------------------------------
# Drift comparison — baseline vs current
# ---------------------------------------------------------------------------

def compare_reports(
    current: dict[str, Any], baseline_path: Path
) -> dict[str, Any]:
    """Compare current report with baseline, return per-metric deltas.

    Positive delta = regression (worse). Negative = improvement.
    """
    if not baseline_path.exists():
        return {"available": False, "reason": "No baseline found"}

    baseline = json.loads(baseline_path.read_text())

    def _get(report: dict[str, Any], *keys: str) -> int | float:
        node: Any = report
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k, 0)
            else:
                return 0
        return node if isinstance(node, int | float) else 0

    metrics = [
        ("ruff_violations", ("checks", "ruff", "violation_count")),
        ("mypy_errors", ("checks", "mypy", "error_count")),
        ("tests_failed", ("checks", "pytest", "tests_failed")),
        ("tests_passed", ("checks", "pytest", "tests_passed")),
        ("arch_violations", ("checks", "architecture", "violation_count")),
        ("forbidden_violations", ("checks", "forbidden_patterns", "violation_count")),
        ("governance_missing", ("checks", "governance_files", "missing_count")),
        ("agent_asset_violations", ("checks", "agent_assets", "violation_count")),
        ("score", ("score", "total")),
    ]

    deltas: dict[str, dict[str, Any]] = {}
    regressions = 0
    improvements = 0

    for name, path_keys in metrics:
        old = _get(baseline, *path_keys)
        new = _get(current, *path_keys)
        delta = new - old
        # For score and tests_passed, positive delta is GOOD (higher is better)
        is_better_when_higher = name in ("tests_passed", "score")
        status = "unchanged"
        if delta > 0:
            status = "improved" if is_better_when_higher else "regressed"
        elif delta < 0:
            status = "regressed" if is_better_when_higher else "improved"

        if status == "regressed":
            regressions += 1
        elif status == "improved":
            improvements += 1

        deltas[name] = {"old": old, "new": new, "delta": delta, "status": status}

    return {
        "available": True,
        "regressions": regressions,
        "improvements": improvements,
        "deltas": deltas,
    }


# ---------------------------------------------------------------------------
# AI repair prompt — structured output to guide AI agent
# ---------------------------------------------------------------------------

def generate_ai_repair_prompt(report: dict[str, Any]) -> str:
    """Generate a structured repair prompt an AI agent can consume."""
    lines: list[str] = []

    lines.append("# AI Self-Repair Task")
    lines.append("")
    lines.append("The health check found the following issues.")
    lines.append("Fix them in priority order. After each fix, re-run:")
    lines.append("  uv run python scripts/ai_health_check.py --report-for-ai")
    lines.append("")
    lines.append("## Report Files")
    lines.append("")
    lines.append("- This file: `.ai/health/repair-prompt.md`")
    lines.append("- Full report (JSON): `.ai/health/latest-report.json`")
    lines.append("- Baseline: `.ai/health/baseline-report.json`")
    lines.append("- History: `.ai/health/history.jsonl`")
    lines.append("- Governance rules: `.ai/CONSTITUTION.md`")
    lines.append("")

    score = report.get("score", {})
    lines.append(f"## Health Score: {score.get('total', '?')}/100")
    lines.append("")

    drift = report.get("drift", {})
    if drift.get("available"):
        lines.append(f"## Drift: {drift.get('regressions', 0)} regressions, "
                      f"{drift.get('improvements', 0)} improvements")
        lines.append("")

    # Collect all violations across all checks
    checks = report.get("checks", {})
    all_violations: list[Violation] = []
    for _name, check in checks.items():
        if isinstance(check, dict):
            all_violations.extend(check.get("violations", []))

    if not all_violations:
        lines.append("No violations found. Project health is good.")
        return "\n".join(lines)

    # Group by rule category
    by_rule: dict[str, list[Violation]] = {}
    for v in all_violations:
        rule = v.get("rule", "unknown")
        category = rule.split("/")[0] if "/" in rule else rule
        by_rule.setdefault(category, []).append(v)

    # Priority order: pytest > arch > forbidden > mypy > ruff > agent > governance
    priority = ["pytest", "arch", "forbidden", "mypy", "ruff", "agent", "governance"]
    ordered_cats = sorted(
        by_rule.keys(), key=lambda c: priority.index(c) if c in priority else 99,
    )

    for i, cat in enumerate(ordered_cats, 1):
        violations = by_rule[cat]
        lines.append(f"## Priority {i}: {cat} ({len(violations)} issues)")
        lines.append("")

        # Show up to 20 violations per category
        for v in violations[:20]:
            lines.append(f"- **{v['file']}:{v['line']}** [{v['rule']}]")
            lines.append(f"  {v['message']}")
            if v.get("fix_hint"):
                lines.append(f"  → Fix: {v['fix_hint']}")
        if len(violations) > 20:
            lines.append(f"  ... and {len(violations) - 20} more")
        lines.append("")

    lines.append("## Repair Rules")
    lines.append("1. Read .ai/CONSTITUTION.md before making changes")
    lines.append("2. Fix failing tests first (they block everything)")
    lines.append("3. Architecture violations next (structural integrity)")
    lines.append("4. Then forbidden patterns → mypy → ruff")
    lines.append("5. After each category, re-run the health check")
    lines.append("6. Do NOT introduce new violations while fixing old ones")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report generation — orchestration
# ---------------------------------------------------------------------------

def generate_report(output_dir: Path, *, quick: bool = False) -> dict[str, Any]:
    """Generate a comprehensive health report."""
    print("🔍 Running AI governance health check (v2.1)...\n")

    results: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "2.1.0",
        "checks": {},
    }

    # Run all checks
    checks: list[tuple[str, Any]] = [
        ("ruff", check_ruff),
        ("mypy", check_mypy),
        ("pytest", lambda: check_tests(quick=quick)),
        ("architecture", check_architecture),
        ("forbidden_patterns", check_forbidden_patterns),
        ("governance_files", check_governance_files),
        ("agent_assets", check_agent_assets),
    ]

    all_passed = True
    total_violations = 0

    for name, check_fn in checks:
        print(f"  Running {name}...")
        result = check_fn()
        results["checks"][name] = result
        passed = result.get("passed", False)
        v_count = result.get("violation_count", 0)
        total_violations += v_count
        if not passed:
            all_passed = False
        status = "✅" if passed else "❌"
        summary = _check_summary(name, result)
        print(f"  {status} {name}: {summary}")

    results["all_passed"] = all_passed
    results["total_violations"] = total_violations

    # Score
    results["score"] = compute_score(results["checks"])
    print(f"\n  📊 Health score: {results['score']['total']}/100")

    # Drift comparison
    baseline_path = output_dir / "baseline-report.json"
    results["drift"] = compare_reports(results, baseline_path)
    if results["drift"].get("available"):
        reg = results["drift"]["regressions"]
        imp = results["drift"]["improvements"]
        if reg > 0:
            print(f"  ⚠️  Drift: {reg} regressions, {imp} improvements vs baseline")
        elif imp > 0:
            print(f"  📈 Drift: {imp} improvements vs baseline")
        else:
            print("  ➡️  No drift from baseline")

    # Write report
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_report(output_dir, results)

    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL CHECKS PASSED — project health is good.")
    else:
        print(f"❌ {total_violations} total violations across all checks.")
        print(f"   Score: {results['score']['total']}/100")
        print("   Run with --report-for-ai for a structured repair plan.")
    print("=" * 60)

    return results


def _check_summary(name: str, result: dict[str, Any]) -> str:
    """One-line summary for a check result."""
    if name == "ruff":
        cats = result.get("by_category", {})
        cat_str = ", ".join(f"{k}:{v}" for k, v in cats.items()) if cats else "clean"
        return f"{result.get('violation_count', 0)} violations ({cat_str})"
    if name == "mypy":
        mods = result.get("by_module", {})
        mod_str = ", ".join(f"{k}:{v}" for k, v in list(mods.items())[:5]) if mods else "clean"
        return f"{result.get('error_count', 0)} errors ({mod_str})"
    if name == "pytest":
        return (
            f"{result.get('tests_passed', 0)} passed, "
            f"{result.get('tests_failed', 0)} failed, "
            f"{result.get('tests_errors', 0)} errors, "
            f"{result.get('tests_skipped', 0)} skipped"
        )
    if name == "architecture":
        return f"{result.get('violation_count', 0)} layer violations"
    if name == "forbidden_patterns":
        return f"{result.get('violation_count', 0)} forbidden patterns"
    if name == "governance_files":
        return (
            f"{result.get('missing_count', 0)} missing, "
            f"{result.get('empty_count', 0)} empty, "
            f"constitution {result.get('constitution_lines', 0)}"
            f"/{result.get('constitution_limit', 500)} lines"
        )
    if name == "agent_assets":
        return (
            f"{result.get('entrypoint_count', 0)} entrypoints, "
            f"{result.get('violation_count', 0)} asset issues"
        )
    return str(result.get("passed", "?"))


def _write_report(output_dir: Path, results: dict[str, Any]) -> None:
    """Write latest report and maintain history ring-buffer."""
    # Strip verbose violation lists for the JSON report (keep summaries)
    report_slim = _slim_report(results)

    # latest-report.json (always overwritten)
    latest = output_dir / "latest-report.json"
    latest.write_text(json.dumps(report_slim, indent=2, default=str) + "\n")
    print(f"\n📄 Report: {latest}")

    # Append to history
    history_path = output_dir / "history.jsonl"
    with history_path.open("a") as f:
        f.write(json.dumps(report_slim, default=str) + "\n")

    # Trim history to MAX_HISTORY entries
    if history_path.exists():
        history_lines = history_path.read_text().splitlines()
        if len(history_lines) > MAX_HISTORY:
            history_path.write_text(
                "\n".join(history_lines[-MAX_HISTORY:]) + "\n"
            )


def _slim_report(results: dict[str, Any]) -> dict[str, Any]:
    """Strip per-violation details for the JSON report file (keep counts)."""
    slim = json.loads(json.dumps(results, default=str))
    for _name, check in slim.get("checks", {}).items():
        if isinstance(check, dict):
            check.pop("violations", None)
    return slim


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point."""
    output_dir = DEFAULT_OUTPUT_DIR
    report_for_ai = False
    compare_only = False
    quick = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--output-dir" and i + 1 < len(args):
            output_dir = Path(args[i + 1])
            i += 2
        elif args[i] == "--report-for-ai":
            report_for_ai = True
            i += 1
        elif args[i] == "--compare":
            compare_only = True
            i += 1
        elif args[i] == "--quick":
            quick = True
            i += 1
        else:
            i += 1

    if compare_only:
        latest = output_dir / "latest-report.json"
        baseline = output_dir / "baseline-report.json"
        if not latest.exists():
            print("❌ No latest-report.json found. Run a scan first.")
            sys.exit(1)
        current = json.loads(latest.read_text())
        drift = compare_reports(current, baseline)
        print(json.dumps(drift, indent=2, default=str))
        sys.exit(0)

    report = generate_report(output_dir, quick=quick)

    if report_for_ai:
        prompt = generate_ai_repair_prompt(report)
        prompt_path = output_dir / "repair-prompt.md"
        prompt_path.write_text(prompt + "\n")
        print(f"\n🤖 AI repair prompt written to {prompt_path}")
        print("   Feed this file to your AI agent to guide self-repair.\n")

    if not report.get("all_passed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
