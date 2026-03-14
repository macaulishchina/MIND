"""WP-0 — CLI namespace separation verification tests."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. mindtest entry point exposes all 8 dev command groups
# ---------------------------------------------------------------------------


class TestMindtestHelp:
    """Verify the mindtest CLI help covers all 8 command groups."""

    EXPECTED_GROUPS = [
        "primitive",
        "access",
        "governance",
        "demo",
        "gate",
        "report",
        "offline",
        "config",
    ]

    def test_mindtest_entry_point_importable(self) -> None:
        """mindtest_main is importable from devcli."""
        from mind.devcli import mindtest_main

        assert callable(mindtest_main)

    def test_mindtest_main_is_mind_main(self) -> None:
        """mindtest_main is the same function as mind_main."""
        from mind.cli import mind_main
        from mind.devcli import mindtest_main

        assert mindtest_main is mind_main

    def test_mindtest_help_covers_all_groups(self) -> None:
        """mindtest -h output mentions all 8 command groups."""
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from mind.cli import mind_main

        out = io.StringIO()
        err = io.StringIO()
        with pytest.raises(SystemExit):
            with redirect_stdout(out), redirect_stderr(err):
                sys.argv = ["mindtest", "-h"]
                mind_main()

        help_text = out.getvalue() + err.getvalue()
        for group in self.EXPECTED_GROUPS:
            assert group in help_text.lower(), (
                f"Expected command group '{group}' not found in mindtest -h output"
            )


# ---------------------------------------------------------------------------
# 2. mind entry point no longer resolves to dev CLI
# ---------------------------------------------------------------------------


class TestMindEntryPointRemoved:
    """Verify that the 'mind' entry point is no longer the dev CLI."""

    def test_pyproject_no_mind_equals_dev_cli(self) -> None:
        """pyproject.toml should not have mind = 'mind.cli:mind_main'."""
        pyproject_path = ROOT / "pyproject.toml"
        content = pyproject_path.read_text()
        # The line 'mind = "mind.cli:mind_main"' should NOT exist
        assert 'mind = "mind.cli:mind_main"' not in content, (
            "pyproject.toml still has 'mind = \"mind.cli:mind_main\"' "
            "(should be renamed to mindtest)"
        )

    def test_pyproject_has_mindtest(self) -> None:
        """pyproject.toml should have mindtest = 'mind.cli:mind_main'."""
        pyproject_path = ROOT / "pyproject.toml"
        content = pyproject_path.read_text()
        assert 'mindtest = "mind.cli:mind_main"' in content


# ---------------------------------------------------------------------------
# 3. Docs have no stale mind primitive/access/gate references
# ---------------------------------------------------------------------------

_STALE_PATTERNS = [
    re.compile(r"uv run mind (?:primitive|access|gate|demo|report|governance|offline|config)\b"),
    re.compile(r"uv run mind-phase-"),
    re.compile(r"uv run mind-postgres-regression"),
    re.compile(r"uv run mind-offline-worker-once"),
]


class TestDocsNoStaleReferences:
    """Grep README and docs/ for stale 'mind primitive' etc. references."""

    def _scan_file(self, path: Path) -> list[str]:
        hits: list[str] = []
        try:
            text = path.read_text()
        except Exception:
            return hits
        for line_no, line in enumerate(text.splitlines(), 1):
            for pat in _STALE_PATTERNS:
                if pat.search(line):
                    hits.append(f"{path}:{line_no}: {line.strip()}")
        return hits

    def test_readme_no_stale_refs(self) -> None:
        readme = ROOT / "README.md"
        hits = self._scan_file(readme)
        assert hits == [], "Stale CLI references in README.md:\n" + "\n".join(hits)

    def test_docs_no_stale_refs(self) -> None:
        docs_dir = ROOT / "docs"
        if not docs_dir.is_dir():
            pytest.skip("docs/ directory not found")
        hits: list[str] = []
        for md in docs_dir.rglob("*.md"):
            hits.extend(self._scan_file(md))
        # Allow docs/reports/ to contain historical references
        non_report_hits = [h for h in hits if "/reports/" not in h]
        assert non_report_hits == [], "Stale CLI references in docs/:\n" + "\n".join(
            non_report_hits
        )


# ---------------------------------------------------------------------------
# 4. pyproject.toml has mindtest-phase-* aliases
# ---------------------------------------------------------------------------


class TestMindtestAliases:
    """All mindtest-phase-* aliases exist in pyproject.toml."""

    EXPECTED_ALIASES = [
        "mindtest-phase-b-gate",
        "mindtest-phase-c-gate",
        "mindtest-phase-d-smoke",
        "mindtest-phase-e-startup",
        "mindtest-phase-e-gate",
        "mindtest-phase-f-manifest",
        "mindtest-phase-f-baselines",
        "mindtest-phase-f-report",
        "mindtest-phase-f-comparison",
        "mindtest-phase-f-gate",
        "mindtest-phase-g-cost-report",
        "mindtest-phase-g-strategy-dev",
        "mindtest-phase-g-gate",
        "mindtest-phase-h-gate",
        "mindtest-phase-i-gate",
        "mindtest-phase-j-gate",
        "mindtest-phase-k-gate",
        "mindtest-phase-k-compatibility-report",
        "mindtest-postgres-regression",
        "mindtest-offline-worker-once",
    ]

    def test_all_mindtest_aliases_present(self) -> None:
        pyproject_path = ROOT / "pyproject.toml"
        content = pyproject_path.read_text()
        for alias in self.EXPECTED_ALIASES:
            assert f'{alias} = "mind.cli:' in content or f"{alias} = 'mind.cli:" in content, (
                f"Missing entry point alias: {alias}"
            )
