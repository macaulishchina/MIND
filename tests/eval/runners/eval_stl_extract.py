"""Single-case STL extraction inspector.

Shows the full pipeline for one eval case:
  conversation → STL raw text → parsed program (refs / statements / evidence)

Usage:
  python tests/eval/runners/eval_stl_extract.py \
    --toml mindt.toml \
    --case tests/eval/cases/owner-feature-001.json

  # Or pass conversation text directly:
  python tests/eval/runners/eval_stl_extract.py \
    --toml mind.toml \
    --conversation 'User: I hope Tom comes to Tokyo'
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.llms.factory import LlmFactory
from mind.runtime_logging import configure_runtime_logging
from mind.stl.parser import parse_program
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)
from mind.utils import parse_messages


# ── helpers ──────────────────────────────────────────────────────────

def _load_case(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _case_to_conversation(case: dict[str, Any]) -> str:
    all_messages: list[dict[str, str]] = []
    for turn in case.get("turns", []):
        all_messages.extend(turn.get("messages", []))
    return parse_messages(all_messages)


def _render_arg(arg: Any) -> str:
    if hasattr(arg, "ref_id"):
        return f"@{arg.ref_id}"
    if hasattr(arg, "prop_id"):
        return f"${arg.prop_id}"
    if hasattr(arg, "items"):
        inner = ", ".join(_render_arg(i) for i in arg.items)
        return f"[{inner}]"
    if hasattr(arg, "predicate") and hasattr(arg, "args"):
        inner = ", ".join(_render_arg(a) for a in arg.args)
        return f"{arg.predicate}({inner})"
    if hasattr(arg, "value"):
        v = arg.value
        if isinstance(v, str):
            return f'"{v}"'
        return str(v)
    return str(arg)


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── main ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect STL extraction for a single eval case or conversation.",
    )
    parser.add_argument(
        "--toml", type=Path, default=_DEFAULT_TEST_TOML,
        help="Config TOML (default: mindt.toml).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--case", type=Path,
        help="Path to a single case JSON file.",
    )
    source.add_argument(
        "--conversation", type=str,
        help="Inline conversation text (e.g. 'User: I like coffee').",
    )
    parser.add_argument(
        "--show-prompt", action="store_true",
        help="Also print the full prompt sent to the LLM.",
    )
    args = parser.parse_args(argv)

    cfg = ConfigManager(toml_path=args.toml).get()
    configure_runtime_logging(cfg.logging)
    llm_cfg = cfg.llm_stages.get("stl_extraction", cfg.llm)
    llm = LlmFactory.create(llm_cfg)

    # ── Build conversation ──
    case = None
    if args.case:
        case = _load_case(args.case.resolve())
        conversation = _case_to_conversation(case)
        print(f"Case: {case.get('id', '?')} — {case.get('description', '')}")
    else:
        conversation = args.conversation

    _print_section("Conversation")
    print(conversation)

    # ── Build prompt ──
    focus_stack_text = format_focus_stack([])
    user_content = STL_EXTRACTION_USER_TEMPLATE.format(
        focus_stack=focus_stack_text,
        conversation=conversation,
    )
    messages = [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    if args.show_prompt:
        _print_section("Prompt (user)")
        print(user_content)

    # ── Call LLM ──
    stl_text = llm.generate(messages=messages)

    _print_section("STL Raw Output")
    print(stl_text)

    # ── Parse ──
    batch_id = str(uuid.uuid4())
    program = parse_program(stl_text, batch_id=batch_id)

    _print_section("Parsed Refs")
    if program.refs:
        for ref in program.refs:
            aliases = f"  aliases={ref.expr.aliases}" if ref.expr.aliases else ""
            print(f"  @{ref.local_id} = {ref.expr.scope.value}/{ref.expr.ref_type}(\"{ref.expr.key}\"){aliases}")
    else:
        print("  (none)")

    _print_section("Parsed Statements")
    if program.statements:
        for stmt in program.statements:
            args_str = ", ".join(_render_arg(a) for a in stmt.args)
            cat = f"  [{stmt.category}]" if stmt.category else ""
            lvl = f"  (level: {stmt.parse_level.value})" if stmt.parse_level else ""
            print(f"  ${stmt.local_id} = {stmt.predicate}({args_str}){cat}{lvl}")
    else:
        print("  (none)")

    _print_section("Parsed Evidence")
    if program.evidence:
        for ev in program.evidence:
            parts = [f"conf={ev.conf}"]
            if ev.span:
                parts.append(f'span="{ev.span}"')
            if ev.residual:
                parts.append(f'residual="{ev.residual}"')
            print(f"  ev(${ev.target_local_id}, {', '.join(parts)})")
    else:
        print("  (none)")

    _print_section("Parsed Notes")
    if program.notes:
        for note in program.notes:
            print(f'  note(${note.target_local_id}, "{note.text}")')
    else:
        print("  (none)")

    if program.failed_lines:
        _print_section("Failed Lines")
        for fl in program.failed_lines:
            print(f"  line {fl.line_number}: {fl.raw_text}")

    # ── Compare with expected (if case) ──
    if case:
        expected_stmts = case.get("expected_statements", [])
        expected_refs = case.get("expected_refs", [])
        expected_ev = case.get("expected_evidence", [])
        has_expected = expected_stmts or expected_refs or expected_ev
        if has_expected:
            _print_section("Expected (from case file)")
            if expected_refs:
                print("  refs:")
                for r in expected_refs:
                    print(f"    {r}")
            if expected_stmts:
                print("  statements:")
                for s in expected_stmts:
                    print(f"    {s}")
            if expected_ev:
                print("  evidence:")
                for e in expected_ev:
                    print(f"    {e}")

    # ── Summary ──
    _print_section("Summary")
    print(f"  refs:       {len(program.refs)}")
    print(f"  statements: {len(program.statements)}")
    print(f"  evidence:   {len(program.evidence)}")
    print(f"  notes:      {len(program.notes)}")
    print(f"  failed:     {len(program.failed_lines)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
