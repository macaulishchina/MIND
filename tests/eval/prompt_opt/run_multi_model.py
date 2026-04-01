#!/usr/bin/env python3
"""Multi-model STL extraction evaluation.

Runs all test cases across multiple models, saves results, and outputs
a comparison summary.

Usage:
    python tests/eval/prompt_opt/run_multi_model.py
"""

import json
import os
import sys
import time
import warnings
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress noise
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from mind.config.manager import ConfigManager
from mind.llms.factory import LlmFactory
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)

# ── Model definitions: (display_name, provider, model_id) ──────────────
MODELS = [
    ("qwen3.5-flash",    "aliyun",  "qwen3.5-flash"),
    ("qwen3.5-plus",     "aliyun",  "qwen3.5-plus"),
    ("gpt-5.4-nano",     "aapi",    "gpt-5.4-nano"),
    ("gpt-5.4",          "aapi",    "gpt-5.4"),
    ("MiniMax-M2.7",     "leihuo",  "MiniMax-M2.7"),
    ("mimo-v2-flash",    "leihuo",  "mimo-v2-flash"),
    ("mimo-v2-pro",      "leihuo",  "mimo-v2-pro"),
    ("glm-5",            "leihuo",  "glm-5"),
    ("deepseek-v3.2",    "leihuo",  "deepseek-v3.2"),
    ("grok-code-fast-1", "leihuo",  "grok-code-fast-1"),
    ("claude-opus-4-6",  "leihuo",  "claude-opus-4-6"),
]


def load_cases(cases_dir: Path) -> list[dict]:
    """Load all po-*.json test cases."""
    cases = []
    for f in sorted(cases_dir.glob("po-*.json")):
        cases.append(json.loads(f.read_text()))
    return cases


def build_prompt(case: dict) -> list[dict]:
    """Build the chat messages for a single case."""
    conv_lines = []
    for turn in case["turns"]:
        for msg in turn["messages"]:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            conv_lines.append(f'{prefix}: {msg["content"]}')
    conv_text = "\n".join(conv_lines)
    user_msg = STL_EXTRACTION_USER_TEMPLATE.format(
        focus_stack=format_focus_stack([]),
        conversation=conv_text,
    )
    return [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def run_single(model_name: str, provider: str, model_id: str,
               cases: list[dict], cfg_mgr: ConfigManager) -> dict:
    """Run all cases for one model. Returns dict of results."""
    cfg = cfg_mgr.get(overrides={"llm": {"provider": provider}})
    cfg.llm.model = model_id
    cfg.logging.ops_llm = False
    cfg.logging.verbose = False

    try:
        llm = LlmFactory.create(cfg.llm)
    except Exception as e:
        return {
            "model": model_name,
            "error": str(e),
            "cases": {},
            "total_ms": 0,
        }

    results = {}
    total_ms = 0

    for case in cases:
        cid = case["id"]
        msgs = build_prompt(case)
        t0 = time.time()
        try:
            output = llm.generate(msgs)
            elapsed = int((time.time() - t0) * 1000)
            results[cid] = {
                "output": output.strip(),
                "ms": elapsed,
                "error": None,
            }
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            results[cid] = {
                "output": "",
                "ms": elapsed,
                "error": str(e),
            }
        total_ms += elapsed

    return {
        "model": model_name,
        "error": None,
        "cases": results,
        "total_ms": total_ms,
    }


def count_stl_lines(output: str) -> dict:
    """Count STL line types in output."""
    lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
    refs = sum(1 for l in lines if l.startswith("@"))
    stmts = sum(1 for l in lines if l.startswith("$"))
    notes = sum(1 for l in lines if l.startswith("note("))
    comments = sum(1 for l in lines if l.startswith("#"))
    other = len(lines) - refs - stmts - notes - comments
    return {
        "total": len(lines),
        "refs": refs,
        "stmts": stmts,
        "notes": notes,
        "comments": comments,
        "other": other,
    }


def print_comparison(all_results: list[dict], cases: list[dict]):
    """Print a markdown comparison table."""
    case_ids = [c["id"] for c in cases]

    # ── Per-case latency table ──
    print("\n## Latency (ms) per case\n")
    header = "| Model |" + "|".join(cid.replace("po-", "") for cid in case_ids) + "| Avg |"
    sep = "|---|" + "|".join("---:" for _ in case_ids) + "|---:|"
    print(header)
    print(sep)
    for r in all_results:
        if r["error"]:
            print(f"| {r['model']} | {'ERR|' * len(case_ids)} ERR |")
            continue
        vals = []
        total = 0
        cnt = 0
        for cid in case_ids:
            cr = r["cases"].get(cid, {})
            ms = cr.get("ms", 0)
            vals.append(str(ms))
            total += ms
            cnt += 1
        avg = total // cnt if cnt else 0
        print(f"| {r['model']} |" + "|".join(vals) + f"| {avg} |")

    # ── Output size table ──
    print("\n## Output size (STL lines) per case\n")
    header = "| Model |" + "|".join(cid.replace("po-", "") for cid in case_ids) + "| Total |"
    sep = "|---|" + "|".join("---:" for _ in case_ids) + "|---:|"
    print(header)
    print(sep)
    for r in all_results:
        if r["error"]:
            print(f"| {r['model']} | {'ERR|' * len(case_ids)} ERR |")
            continue
        vals = []
        grand = 0
        for cid in case_ids:
            cr = r["cases"].get(cid, {})
            out = cr.get("output", "")
            stats = count_stl_lines(out)
            vals.append(str(stats["total"]))
            grand += stats["total"]
        print(f"| {r['model']} |" + "|".join(vals) + f"| {grand} |")

    # ── Error summary ──
    print("\n## Errors\n")
    any_err = False
    for r in all_results:
        if r["error"]:
            print(f"- **{r['model']}**: {r['error']}")
            any_err = True
            continue
        for cid in case_ids:
            cr = r["cases"].get(cid, {})
            if cr.get("error"):
                print(f"- **{r['model']}** / {cid}: {cr['error']}")
                any_err = True
    if not any_err:
        print("No errors.")


def main():
    toml_path = PROJECT_ROOT / "mindt.toml"
    cases_dir = PROJECT_ROOT / "tests" / "eval" / "prompt_opt" / "cases"
    output_dir = PROJECT_ROOT / "tests" / "eval" / "prompt_opt" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_mgr = ConfigManager(toml_path=toml_path)
    cases = load_cases(cases_dir)
    print(f"Loaded {len(cases)} cases, testing {len(MODELS)} models\n")

    all_results = []

    # Run models in parallel (thread-per-model)
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        futures = {}
        for name, provider, model_id in MODELS:
            f = pool.submit(run_single, name, provider, model_id, cases, cfg_mgr)
            futures[f] = name

        for f in as_completed(futures):
            name = futures[f]
            try:
                result = f.result()
                all_results.append(result)
                n_ok = sum(1 for v in result["cases"].values() if not v.get("error"))
                n_err = sum(1 for v in result["cases"].values() if v.get("error"))
                ms = result["total_ms"]
                if result["error"]:
                    print(f"  ✗ {name}: FAILED — {result['error']}")
                else:
                    print(f"  ✓ {name}: {n_ok} ok, {n_err} err, {ms}ms total")
            except Exception as e:
                print(f"  ✗ {name}: EXCEPTION — {e}")
                all_results.append({"model": name, "error": str(e), "cases": {}, "total_ms": 0})

    # Sort by model order
    model_order = {name: i for i, (name, _, _) in enumerate(MODELS)}
    all_results.sort(key=lambda r: model_order.get(r["model"], 999))

    # Save raw results
    for r in all_results:
        fname = r["model"].replace("/", "_").replace(" ", "_")
        (output_dir / f"{fname}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2)
        )

    # Print comparison
    print_comparison(all_results, cases)

    # Save combined
    (output_dir / "_all_results.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2)
    )
    print(f"\nResults saved to {output_dir}/")


if __name__ == "__main__":
    main()
