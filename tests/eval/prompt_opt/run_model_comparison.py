#!/usr/bin/env python3
"""Run all 20 po-* cases across 11 models (all leihuo), save results, print comparison."""

import json, time, warnings, logging, sys, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

# Silence everything
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mind.config.manager import ConfigManager
from mind.llms.factory import LlmFactory
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)

MODELS = [
    "gpt-5.4-nano",
    "gpt-5.4",
    "MiniMax-M2.7",
    "mimo-v2-flash",
    "mimo-v2-pro",
    "glm-5",
    "deepseek-v3.2",
    "grok-code-fast-1",
    "claude-opus-4-6",
]

SPEED_CUTOFF_MS = 10_000  # skip models slower than 10s on probe case

CASES_DIR = Path(__file__).resolve().parents[1] / "prompt_opt" / "cases"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "prompt_opt" / "results"


def build_user_msg(case: dict) -> str:
    conv_lines = []
    for turn in case["turns"]:
        for msg in turn["messages"]:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            conv_lines.append(f'{prefix}: {msg["content"]}')
    conv_text = "\n".join(conv_lines)
    return STL_EXTRACTION_USER_TEMPLATE.format(
        focus_stack=format_focus_stack([]), conversation=conv_text
    )


def run_one(model: str, case_file: Path, toml_path: Path) -> dict:
    """Run a single (model, case) pair. Returns result dict."""
    case = json.loads(case_file.read_text())
    cid = case["id"]
    user_msg = build_user_msg(case)
    msgs = [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    cfg_mgr = ConfigManager(toml_path=toml_path)
    cfg = cfg_mgr.get(overrides={"llm": {"provider": "leihuo"}})
    cfg.llm.model = model
    cfg.logging.ops_llm = False
    cfg.logging.verbose = False
    llm = LlmFactory.create(cfg.llm)

    t0 = time.time()
    try:
        result = llm.generate(msgs)
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "model": model,
            "case_id": cid,
            "status": "ok",
            "elapsed_ms": elapsed_ms,
            "output": result.strip(),
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "model": model,
            "case_id": cid,
            "status": "error",
            "elapsed_ms": elapsed_ms,
            "output": str(e),
        }


def speed_probe(toml_path: Path, probe_case: Path) -> list[str]:
    """Test each model with one case. Return models that respond within SPEED_CUTOFF_MS."""
    print(f"\n{'='*60}", flush=True)
    print("SPEED PROBE — testing each model with one case", flush=True)
    print(f"Cutoff: {SPEED_CUTOFF_MS}ms", flush=True)
    print(f"{'='*60}", flush=True)

    fast_models = []
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        futures = {pool.submit(run_one, m, probe_case, toml_path): m for m in MODELS}
        for fut in as_completed(futures):
            m = futures[fut]
            r = fut.result()
            passed = r["status"] == "ok" and r["elapsed_ms"] <= SPEED_CUTOFF_MS
            tag = "PASS" if passed else "SKIP"
            print(f"  {tag} {m:<22} {r['elapsed_ms']:>6}ms  {r['status']}", flush=True)
            if passed:
                fast_models.append(m)

    # Preserve original ordering
    fast_models = [m for m in MODELS if m in fast_models]
    print(f"\nProbe result: {len(fast_models)}/{len(MODELS)} models passed", flush=True)
    print(f"Fast models: {fast_models}\n", flush=True)
    return fast_models


def main():
    toml_path = Path("mindt.toml")
    case_files = sorted(CASES_DIR.glob("po-*.json"))

    # Speed probe
    probe_case = CASES_DIR / "po-basic-001.json"
    active_models = speed_probe(toml_path, probe_case)
    if not active_models:
        print("No models passed speed probe. Exiting.", flush=True)
        return

    print(f"Cases: {len(case_files)}, Models: {len(active_models)}", flush=True)
    print(f"Total runs: {len(case_files) * len(active_models)}", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Build all tasks
    tasks = []
    for model in active_models:
        for cf in case_files:
            tasks.append((model, cf))

    results = []
    with ThreadPoolExecutor(max_workers=len(active_models)) as pool:
        futures = {}
        for model, cf in tasks:
            fut = pool.submit(run_one, model, cf, toml_path)
            futures[fut] = (model, cf.stem)

        done_count = 0
        total = len(futures)
        for fut in as_completed(futures):
            done_count += 1
            r = fut.result()
            results.append(r)
            status_icon = "✓" if r["status"] == "ok" else "✗"
            if done_count % 10 == 0 or done_count == total:
                print(f"  [{done_count}/{total}] {status_icon} {r['model']} / {r['case_id']} ({r['elapsed_ms']}ms)", flush=True)

    # Save per-model results
    by_model = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)

    for model, model_results in by_model.items():
        model_results.sort(key=lambda x: x["case_id"])
        safe_name = model.replace("/", "_").replace(".", "_")
        out_file = OUTPUT_DIR / f"{safe_name}.json"
        out_file.write_text(json.dumps(model_results, ensure_ascii=False, indent=2))

    # Save combined results
    combined_file = OUTPUT_DIR / "all_results.json"
    results.sort(key=lambda x: (x["model"], x["case_id"]))
    combined_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # Print summary table
    print("\n" + "=" * 100)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 100)

    # Compute per-model stats
    model_stats = {}
    for model in active_models:
        mr = [r for r in results if r["model"] == model]
        ok = [r for r in mr if r["status"] == "ok"]
        errors = [r for r in mr if r["status"] == "error"]
        avg_ms = sum(r["elapsed_ms"] for r in ok) / len(ok) if ok else 0
        total_stmts = 0
        for r in ok:
            lines = [l for l in r["output"].split("\n") if l.strip() and not l.strip().startswith("#")]
            total_stmts += len(lines)
        avg_stmts = total_stmts / len(ok) if ok else 0
        model_stats[model] = {
            "ok": len(ok),
            "errors": len(errors),
            "avg_ms": avg_ms,
            "avg_stmts": avg_stmts,
            "total_stmts": total_stmts,
        }

    # Print
    header = f"{'Model':<22} {'OK':>4} {'Err':>4} {'Avg ms':>8} {'Avg Stmts':>10} {'Total Stmts':>12}"
    print(header)
    print("-" * len(header))
    for model in active_models:
        s = model_stats[model]
        print(
            f"{model:<22} {s['ok']:>4} {s['errors']:>4} {s['avg_ms']:>8.0f} {s['avg_stmts']:>10.1f} {s['total_stmts']:>12}"
        )

    # Per-case breakdown: count output lines as proxy for completeness
    case_ids = sorted(set(r["case_id"] for r in results))
    print("\n\nPER-CASE OUTPUT LINES (non-comment, non-empty):")
    print(f"{'Case':<28}", end="")
    for model in active_models:
        short = model[:10]
        print(f" {short:>10}", end="")
    print()
    print("-" * (28 + 11 * len(active_models)))
    for cid in case_ids:
        print(f"{cid:<28}", end="")
        for model in active_models:
            r = next((x for x in results if x["model"] == model and x["case_id"] == cid), None)
            if r and r["status"] == "ok":
                lines = [l for l in r["output"].split("\n") if l.strip() and not l.strip().startswith("#")]
                print(f" {len(lines):>10}", end="")
            else:
                print(f" {'ERR':>10}", end="")
        print()

    print(f"\nResults saved to: {OUTPUT_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
