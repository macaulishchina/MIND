"""A/B runner for UPDATE_DECISION prompt variants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from tests.eval.decision_opt.ab import evaluate_ab
from tests.eval.decision_opt.core import (
    DEFAULT_CASES_DIR,
    DEFAULT_OUTPUT_DIR,
    _DEFAULT_TEST_TOML,
    _configure_runner_logging,
    build_report,
    create_eval_llm,
    current_runtime_prompt,
    load_cases,
    prompt_metadata,
    render_summary,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toml", dest="toml_path", default=_DEFAULT_TEST_TOML)
    parser.add_argument("--case", dest="case_source", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--model", default=None, help="Shared provider:model for both arms")
    parser.add_argument("--model-a", default=None, help="provider:model override for arm A")
    parser.add_argument("--model-b", default=None, help="provider:model override for arm B")
    parser.add_argument("--judge", default=None, help="Optional provider:model judge")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--prompt-file-a", type=Path, default=None)
    parser.add_argument("--prompt-file-b", type=Path, default=None)
    parser.add_argument("--label-a", default="runtime-control")
    parser.add_argument("--label-b", default="candidate")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--json", action="store_true", help="Print the JSON report")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def _read_prompt(path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_mgr = ConfigManager(toml_path=args.toml_path)
    cfg = cfg_mgr.get()
    _configure_runner_logging(cfg)

    cases = load_cases(args.case_source)
    if args.limit > 0:
        cases = cases[: args.limit]

    prompt_a = _read_prompt(args.prompt_file_a, current_runtime_prompt())
    prompt_b = _read_prompt(args.prompt_file_b, prompt_a)
    model_a = args.model_a or args.model
    model_b = args.model_b or args.model

    case_results = evaluate_ab(
        cases=cases,
        prompt_a=prompt_a,
        prompt_b=prompt_b,
        llm_factory_a=lambda: create_eval_llm(cfg_mgr, model_a),
        llm_factory_b=lambda: create_eval_llm(cfg_mgr, model_b),
        prompt_label_a=args.label_a,
        prompt_label_b=args.label_b,
        judge_factory=(
            None
            if args.skip_judge or not args.judge
            else (lambda: create_eval_llm(cfg_mgr, args.judge))
        ),
        concurrency=max(1, args.concurrency),
    )

    report = build_report(
        case_results=case_results,
        prompt_a=prompt_metadata(
            args.label_a,
            prompt_a,
            model_a or cfg.llm_stages.get("decision", cfg.llm).model,
        ),
        prompt_b=prompt_metadata(
            args.label_b,
            prompt_b,
            model_b or cfg.llm_stages.get("decision", cfg.llm).model,
        ),
        judge_model=None if args.skip_judge else args.judge,
    )

    output_path = args.output
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        print(render_summary(report, output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

