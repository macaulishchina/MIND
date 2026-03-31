from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.llms.factory import LlmFactory
from mind.prompts import UPDATE_DECISION_SYSTEM_PROMPT, UPDATE_DECISION_USER_TEMPLATE
from mind.stl.prompt import STL_EXTRACTION_SYSTEM_PROMPT, STL_EXTRACTION_USER_TEMPLATE


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _bool_arg(value: str) -> bool:
    lowered = value.strip().casefold()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def _build_messages(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    if args.stage == "stl_extraction":
        return (
            [
                {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": STL_EXTRACTION_USER_TEMPLATE.format(
                        focus_stack=args.focus_stack,
                        conversation=args.conversation,
                    ),
                },
            ],
            None,
        )

    if args.stage == "decision":
        return (
            [
                {"role": "system", "content": UPDATE_DECISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": UPDATE_DECISION_USER_TEMPLATE.format(
                        existing_memories=args.existing_memories,
                        new_fact=args.new_fact,
                    ),
                },
            ],
            {"type": "json_object"},
        )

    return (
        [
            {"role": "system", "content": args.system_prompt},
            {"role": "user", "content": args.user_prompt},
        ],
        None,
    )


def _build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    if not any(
        value is not None
        for value in (args.provider, args.model, args.temperature, args.batch)
    ):
        return {}

    stage_key = None if args.stage == "llm" else args.stage
    override_block: dict[str, Any] = {}
    if args.provider is not None:
        override_block["provider"] = args.provider
    if args.model is not None:
        override_block["model"] = args.model
    if args.temperature is not None:
        override_block["temperature"] = args.temperature
    if args.batch is not None:
        override_block["batch"] = args.batch

    if stage_key is None:
        return {"llm": override_block}
    return {"llm": {stage_key: override_block}}


def _resolve_llm_config(args: argparse.Namespace):
    cfg = ConfigManager(toml_path=args.toml).get(overrides=_build_overrides(args))
    if args.stage == "llm":
        return cfg.llm
    return cfg.llm_stages.get(args.stage, cfg.llm)


def _summary(latencies: list[float]) -> dict[str, float]:
    return {
        "min_s": min(latencies),
        "max_s": max(latencies),
        "avg_s": statistics.mean(latencies),
        "median_s": statistics.median(latencies),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a simple latency check against one LLM stage.",
    )
    parser.add_argument(
        "--toml",
        type=Path,
        default=_DEFAULT_TEST_TOML,
        help="Path to config TOML (default: mindt.toml)",
    )
    parser.add_argument(
        "--stage",
        choices=("llm", "stl_extraction", "decision"),
        default="stl_extraction",
        help="Which LLM config/stage to measure.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of timed calls to run. Default: 3.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="Warmup calls before timing. Default: 0.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Optional provider override for the selected stage.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional model override for the selected stage.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional temperature override for the selected stage.",
    )
    parser.add_argument(
        "--batch",
        type=_bool_arg,
        default=None,
        help="Optional batch override for the selected stage: true/false.",
    )
    parser.add_argument(
        "--conversation",
        type=str,
        default="User: My friend Green is a football player",
        help="Conversation text for --stage stl_extraction.",
    )
    parser.add_argument(
        "--focus-stack",
        type=str,
        default="",
        help="Focus stack text for --stage stl_extraction.",
    )
    parser.add_argument(
        "--existing-memories",
        type=str,
        default="[0] [friend:green] relation_to_owner=friend",
        help="Existing memories block for --stage decision.",
    )
    parser.add_argument(
        "--new-fact",
        type=str,
        default="[friend:green] occupation=football player",
        help="New fact text for --stage decision.",
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default="You are a helpful assistant. Reply in one short sentence.",
        help="System prompt for --stage llm.",
    )
    parser.add_argument(
        "--user-prompt",
        type=str,
        default="Say hello.",
        help="User prompt for --stage llm.",
    )
    parser.add_argument(
        "--show-response",
        action="store_true",
        help="Print the full response for each timed run.",
    )
    args = parser.parse_args(argv)

    if args.runs <= 0:
        parser.error("--runs must be >= 1")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")

    llm_cfg = _resolve_llm_config(args)
    llm = LlmFactory.create(llm_cfg)
    messages, response_format = _build_messages(args)

    print(f"config: {_display_path(args.toml)}")
    print(f"stage: {args.stage}")
    print(f"provider: {llm_cfg.provider}")
    print(f"protocols: {llm_cfg.protocols}")
    print(f"model: {llm_cfg.model}")
    print(f"batch: {llm_cfg.batch}")
    print(f"temperature: {llm_cfg.temperature}")
    print(f"warmup: {args.warmup}")
    print(f"runs: {args.runs}")

    for index in range(args.warmup):
        llm.generate(messages=messages, response_format=response_format)
        print(f"warmup {index + 1}/{args.warmup}: done")

    latencies: list[float] = []
    for index in range(args.runs):
        start = time.perf_counter()
        response = llm.generate(messages=messages, response_format=response_format)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        preview = response.replace("\n", " ").strip()
        if not args.show_response and len(preview) > 120:
            preview = preview[:117] + "..."

        print(
            f"run {index + 1}/{args.runs}: {elapsed:.3f}s | "
            f"response_chars={len(response)}"
        )
        if args.show_response:
            print(response)
        else:
            print(f"  preview: {preview or '<empty>'}")

    stats = _summary(latencies)
    print("summary:")
    print(f"  min: {stats['min_s']:.3f}s")
    print(f"  max: {stats['max_s']:.3f}s")
    print(f"  avg: {stats['avg_s']:.3f}s")
    print(f"  median: {stats['median_s']:.3f}s")
    print(json.dumps({"latencies_s": latencies, **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
