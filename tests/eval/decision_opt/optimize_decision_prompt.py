"""CLI wrapper for offline decision prompt optimization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from tests.eval.decision_opt.core import (
    DEFAULT_CASES_DIR,
    _DEFAULT_TEST_TOML,
    _configure_runner_logging,
    create_eval_llm,
    current_runtime_prompt,
    load_cases,
)
from tests.eval.decision_opt.optimizer import (
    default_artifacts_dir,
    promote_runtime_prompt,
    run_optimization_rounds,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toml", dest="toml_path", default=_DEFAULT_TEST_TOML)
    parser.add_argument("--case", dest="case_source", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--eval-model", default=None, help="provider:model for decision evaluation")
    parser.add_argument("--optimizer-model", default=None, help="provider:model for candidate generation")
    parser.add_argument("--judge", default=None, help="Optional provider:model for judge scoring")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    parser.add_argument("--seed-prompt-file", type=Path, default=None)
    parser.add_argument("--promote", action="store_true", help="Write the winning prompt back to mind/prompts.py")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg_mgr = ConfigManager(toml_path=args.toml_path)
    cfg = cfg_mgr.get()
    _configure_runner_logging(cfg)

    cases = load_cases(args.case_source)
    if args.limit > 0:
        cases = cases[: args.limit]

    seed_prompt = (
        args.seed_prompt_file.read_text(encoding="utf-8")
        if args.seed_prompt_file is not None
        else current_runtime_prompt()
    )
    artifacts_dir = args.artifacts_dir or default_artifacts_dir()
    summary = run_optimization_rounds(
        cases=cases,
        control_prompt=seed_prompt,
        llm_factory=lambda: create_eval_llm(cfg_mgr, args.eval_model),
        prompt_label="runtime-control",
        rounds=max(1, args.rounds),
        artifacts_dir=artifacts_dir,
        concurrency=max(1, args.concurrency),
        judge_factory=(
            None
            if args.skip_judge or not args.judge
            else (lambda: create_eval_llm(cfg_mgr, args.judge))
        ),
        optimizer_llm_factory=(
            None
            if not args.optimizer_model
            else (lambda: create_eval_llm(cfg_mgr, args.optimizer_model))
        ),
    )

    if args.promote and summary["final_prompt"] != current_runtime_prompt():
        promote_runtime_prompt(PROJECT_ROOT / "mind" / "prompts.py", summary["final_prompt"])

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

