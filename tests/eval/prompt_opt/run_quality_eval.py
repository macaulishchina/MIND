#!/usr/bin/env python3
"""Evaluate quality of saved model comparison results using LLM-as-judge.

Reads all_results.json + case files (golden_stl), sends each (model, case) output
to the judge LLM, collects 7-dimension scores, and produces a quality ranking.
"""

import json, time, os, sys, warnings, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mind.config.manager import ConfigManager
from mind.llms.factory import LlmFactory
from tests.eval.prompt_opt.judge import evaluate as judge_evaluate, DIMENSIONS, DIMENSION_WEIGHTS

CASES_DIR = Path(__file__).resolve().parent / "cases"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Judge model — use gpt-5.4-nano via leihuo (fast, cheap, good enough for judging)
JUDGE_MODEL = "gpt-5.4-nano"
JUDGE_PROVIDER = "leihuo"


def build_conversation_text(case: dict) -> str:
    lines = []
    for turn in case["turns"]:
        for msg in turn["messages"]:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f'{prefix}: {msg["content"]}')
    return "\n".join(lines)


def judge_one(judge_llm, case: dict, actual_stl: str) -> dict:
    """Judge a single (case, output) pair. Returns scores dict."""
    conversation = build_conversation_text(case)
    golden_stl = case.get("golden_stl", "")

    result = judge_evaluate(judge_llm, conversation, golden_stl, actual_stl)
    return {
        "weighted_score": result.weighted_score,
        "scores": {dim: {"score": ds.score, "reason": ds.reason} for dim, ds in result.scores.items()},
        "overall_comment": result.overall_comment,
        "parse_error": result.parse_error,
    }


def main():
    toml_path = Path("mindt.toml")

    # Load results
    all_results_file = RESULTS_DIR / "all_results.json"
    if not all_results_file.exists():
        print("ERROR: all_results.json not found. Run run_model_comparison.py first.")
        return
    all_results = json.loads(all_results_file.read_text())

    # Load case files (for golden_stl and conversation)
    case_cache = {}
    for cf in sorted(CASES_DIR.glob("po-*.json")):
        case = json.loads(cf.read_text())
        case_cache[case["id"]] = case

    # Filter to successful results only
    ok_results = [r for r in all_results if r["status"] == "ok"]
    models = sorted(set(r["model"] for r in ok_results))

    print(f"Quality evaluation: {len(ok_results)} results across {len(models)} models", flush=True)
    print(f"Judge model: {JUDGE_MODEL} via {JUDGE_PROVIDER}", flush=True)
    print(f"Dimensions: {', '.join(DIMENSIONS)}", flush=True)
    print(f"{'='*80}", flush=True)

    # Create judge LLM
    cfg_mgr = ConfigManager(toml_path=toml_path)
    cfg = cfg_mgr.get(overrides={"llm": {"provider": JUDGE_PROVIDER}})
    cfg.llm.model = JUDGE_MODEL
    cfg.logging.ops_llm = False
    cfg.logging.verbose = False
    judge_llm = LlmFactory.create(cfg.llm)

    # Run all judgments in parallel (judge is fast)
    judge_results = []  # list of {model, case_id, weighted_score, scores, ...}

    def judge_task(r):
        case = case_cache.get(r["case_id"])
        if not case:
            return None
        t0 = time.time()
        jr = judge_one(judge_llm, case, r["output"])
        elapsed = int((time.time() - t0) * 1000)
        return {
            "model": r["model"],
            "case_id": r["case_id"],
            "elapsed_ms": elapsed,
            **jr,
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(judge_task, r): r for r in ok_results}
        done = 0
        total = len(futures)
        for fut in as_completed(futures):
            done += 1
            jr = fut.result()
            if jr:
                judge_results.append(jr)
                if done % 20 == 0 or done == total:
                    print(f"  [{done}/{total}] {jr['model']}/{jr['case_id']} -> {jr['weighted_score']:.2f} ({jr['elapsed_ms']}ms)", flush=True)

    # Save raw judge results
    judge_output = RESULTS_DIR / "quality_results.json"
    judge_results.sort(key=lambda x: (x["model"], x["case_id"]))
    judge_output.write_text(json.dumps(judge_results, ensure_ascii=False, indent=2))
    print(f"\nRaw judge results saved to: {judge_output}", flush=True)

    # ── Per-model quality summary ──
    print(f"\n{'='*100}", flush=True)
    print("QUALITY EVALUATION RESULTS", flush=True)
    print(f"{'='*100}", flush=True)

    model_quality = {}
    for model in models:
        mr = [r for r in judge_results if r["model"] == model]
        if not mr:
            continue
        ws = [r["weighted_score"] for r in mr]
        avg_ws = sum(ws) / len(ws)

        # Per-dimension averages
        dim_avgs = {}
        for dim in DIMENSIONS:
            scores = [r["scores"][dim]["score"] for r in mr if dim in r["scores"]]
            dim_avgs[dim] = sum(scores) / len(scores) if scores else 0

        model_quality[model] = {
            "avg_weighted": avg_ws,
            "count": len(mr),
            "dim_avgs": dim_avgs,
        }

    # Print summary table
    print(f"\n{'Model':<22} {'Avg Score':>10}", end="")
    for dim in DIMENSIONS:
        short = dim[:8]
        print(f" {short:>8}", end="")
    print()
    print("-" * (22 + 10 + 9 * len(DIMENSIONS)))

    for model in sorted(model_quality.keys(), key=lambda m: -model_quality[m]["avg_weighted"]):
        mq = model_quality[model]
        print(f"{model:<22} {mq['avg_weighted']:>10.2f}", end="")
        for dim in DIMENSIONS:
            print(f" {mq['dim_avgs'][dim]:>8.1f}", end="")
        print()

    # ── Quality ranking ──
    print(f"\n{'='*60}")
    print("QUALITY RANKING (weighted score, higher=better)")
    print(f"{'='*60}")
    ranked = sorted(model_quality.items(), key=lambda x: -x[1]["avg_weighted"])
    for i, (model, mq) in enumerate(ranked, 1):
        print(f"  {i}. {model:<22} {mq['avg_weighted']:.2f}/10")

    # ── Per-dimension rankings ──
    for dim in DIMENSIONS:
        weight = DIMENSION_WEIGHTS[dim]
        print(f"\n  [{dim}] (weight {weight:.0%})")
        for i, (model, mq) in enumerate(
            sorted(model_quality.items(), key=lambda x: -x[1]["dim_avgs"][dim]), 1
        ):
            print(f"    {i}. {model:<22} {mq['dim_avgs'][dim]:.1f}/10")

    # ── Per-case breakdown ──
    case_ids = sorted(set(r["case_id"] for r in judge_results))
    print(f"\n{'='*100}")
    print("PER-CASE QUALITY SCORES (weighted)")
    print(f"{'='*100}")
    print(f"{'Case':<28}", end="")
    for model in sorted(model_quality.keys(), key=lambda m: -model_quality[m]["avg_weighted"]):
        print(f" {model[:10]:>10}", end="")
    print()
    print("-" * (28 + 11 * len(model_quality)))
    for cid in case_ids:
        print(f"{cid:<28}", end="")
        for model in sorted(model_quality.keys(), key=lambda m: -model_quality[m]["avg_weighted"]):
            r = next((x for x in judge_results if x["model"] == model and x["case_id"] == cid), None)
            if r:
                print(f" {r['weighted_score']:>10.2f}", end="")
            else:
                print(f" {'N/A':>10}", end="")
        print()

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
