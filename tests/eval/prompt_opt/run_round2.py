#!/usr/bin/env python3
"""Round 2: Model comparison with 10s timeout + LLM-as-judge quality evaluation.

Models: gpt-5.4-nano, gpt-5.4, gpt-5.4-mini, mimo-v2-flash, mimo-v2-pro,
        deepseek-v3.2, MiniMax-M2.7-highspeed
All via leihuo provider. 10s hard timeout per extraction request.
"""

import json, time, warnings, logging, sys, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

os.environ["PYTHONUNBUFFERED"] = "1"
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
from tests.eval.prompt_opt.judge import (
    evaluate as judge_evaluate,
    DIMENSIONS,
    DIMENSION_WEIGHTS,
)

# ── Config ───────────────────────────────────────────────────────────

MODELS = [
    "claude-opus-4-6",
    "gpt-5.4-nano",
    "gpt-5.4",
    "gpt-5.4-mini",
    "mimo-v2-flash",
    "mimo-v2-pro",
    "deepseek-v3.2",
    "MiniMax-M2.7-highspeed",
]

REQUEST_TIMEOUT_S = 10  # hard timeout per extraction call

CASES_DIR = Path(__file__).resolve().parents[1] / "prompt_opt" / "cases"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "prompt_opt" / "results_r2"

JUDGE_MODEL = "gpt-5.4-nano"
JUDGE_PROVIDER = "leihuo"

# ── Helpers ──────────────────────────────────────────────────────────


def build_user_msg(case: dict) -> str:
    conv_lines = []
    for turn in case["turns"]:
        for msg in turn["messages"]:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            conv_lines.append(f'{prefix}: {msg["content"]}')
    return STL_EXTRACTION_USER_TEMPLATE.format(
        focus_stack=format_focus_stack([]),
        conversation="\n".join(conv_lines),
    )


def build_conversation_text(case: dict) -> str:
    lines = []
    for turn in case["turns"]:
        for msg in turn["messages"]:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f'{prefix}: {msg["content"]}')
    return "\n".join(lines)


def _call_llm(model: str, msgs: list, toml_path: Path) -> str:
    """Make a single LLM call (blocking). Called inside a thread."""
    cfg_mgr = ConfigManager(toml_path=toml_path)
    cfg = cfg_mgr.get(overrides={"llm": {"provider": "leihuo"}})
    cfg.llm.model = model
    cfg.logging.ops_llm = False
    cfg.logging.verbose = False
    llm = LlmFactory.create(cfg.llm)
    return llm.generate(msgs)


def run_one(model: str, case_file: Path, toml_path: Path) -> dict:
    """Run extraction for one (model, case) with REQUEST_TIMEOUT_S enforcement."""
    case = json.loads(case_file.read_text())
    cid = case["id"]
    user_msg = build_user_msg(case)
    msgs = [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    t0 = time.time()
    # Use a single-thread pool to enforce hard timeout
    with ThreadPoolExecutor(max_workers=1) as inner:
        fut = inner.submit(_call_llm, model, msgs, toml_path)
        try:
            result = fut.result(timeout=REQUEST_TIMEOUT_S)
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "model": model,
                "case_id": cid,
                "status": "ok",
                "elapsed_ms": elapsed_ms,
                "output": result.strip(),
            }
        except FuturesTimeout:
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "model": model,
                "case_id": cid,
                "status": "timeout",
                "elapsed_ms": elapsed_ms,
                "output": f"TIMEOUT after {REQUEST_TIMEOUT_S}s",
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


# ── Main ─────────────────────────────────────────────────────────────


def main():
    toml_path = Path("mindt.toml")
    case_files = sorted(CASES_DIR.glob("po-*.json"))

    # Load case data for judging later
    case_cache = {}
    for cf in case_files:
        c = json.loads(cf.read_text())
        case_cache[c["id"]] = c

    print(f"{'='*80}", flush=True)
    print(f"ROUND 2 — MODEL COMPARISON (timeout={REQUEST_TIMEOUT_S}s per request)", flush=True)
    print(f"Models: {MODELS}", flush=True)
    print(f"Cases: {len(case_files)}, Total runs: {len(case_files) * len(MODELS)}", flush=True)
    print(f"{'='*80}\n", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Extraction ──────────────────────────────────────────

    print("PHASE 1: STL Extraction", flush=True)
    print("-" * 40, flush=True)

    tasks = [(m, cf) for m in MODELS for cf in case_files]
    results = []

    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
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
            icon = "✓" if r["status"] == "ok" else ("⏱" if r["status"] == "timeout" else "✗")
            if done_count % 10 == 0 or done_count == total:
                print(f"  [{done_count}/{total}] {icon} {r['model']:<26} {r['case_id']:<28} {r['elapsed_ms']:>6}ms  {r['status']}", flush=True)

    # Save extraction results
    results.sort(key=lambda x: (x["model"], x["case_id"]))
    (OUTPUT_DIR / "extraction_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)
    )

    # ── Phase 1 Summary ──────────────────────────────────────────────

    print(f"\n{'='*100}", flush=True)
    print("EXTRACTION SUMMARY", flush=True)
    print(f"{'='*100}", flush=True)

    model_stats = {}
    for model in MODELS:
        mr = [r for r in results if r["model"] == model]
        ok = [r for r in mr if r["status"] == "ok"]
        timeouts = [r for r in mr if r["status"] == "timeout"]
        errors = [r for r in mr if r["status"] == "error"]
        ok_ms = [r["elapsed_ms"] for r in ok]
        total_stmts = 0
        for r in ok:
            lines = [l for l in r["output"].split("\n") if l.strip() and not l.strip().startswith("#")]
            total_stmts += len(lines)
        model_stats[model] = {
            "ok": len(ok),
            "timeouts": len(timeouts),
            "errors": len(errors),
            "avg_ms": sum(ok_ms) / len(ok_ms) if ok_ms else 0,
            "median_ms": sorted(ok_ms)[len(ok_ms) // 2] if ok_ms else 0,
            "min_ms": min(ok_ms) if ok_ms else 0,
            "max_ms": max(ok_ms) if ok_ms else 0,
            "avg_stmts": total_stmts / len(ok) if ok else 0,
            "total_stmts": total_stmts,
            "timeout_cases": [r["case_id"] for r in timeouts],
            "error_cases": [r["case_id"] for r in errors],
        }

    header = f"{'Model':<28} {'OK':>3} {'T/O':>3} {'Err':>3} {'Avg ms':>8} {'Med ms':>8} {'Max ms':>8} {'Avg Stmts':>10}"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for model in MODELS:
        s = model_stats[model]
        print(
            f"{model:<28} {s['ok']:>3} {s['timeouts']:>3} {s['errors']:>3} "
            f"{s['avg_ms']:>8.0f} {s['median_ms']:>8} {s['max_ms']:>8} {s['avg_stmts']:>10.1f}",
            flush=True,
        )

    # ── Phase 2: Quality Evaluation ──────────────────────────────────

    ok_results = [r for r in results if r["status"] == "ok"]
    print(f"\n{'='*80}", flush=True)
    print(f"PHASE 2: Quality Evaluation (judge={JUDGE_MODEL}, {len(ok_results)} outputs)", flush=True)
    print("-" * 40, flush=True)

    cfg_mgr = ConfigManager(toml_path=toml_path)
    cfg = cfg_mgr.get(overrides={"llm": {"provider": JUDGE_PROVIDER}})
    cfg.llm.model = JUDGE_MODEL
    cfg.logging.ops_llm = False
    cfg.logging.verbose = False
    judge_llm = LlmFactory.create(cfg.llm)

    def judge_task(r):
        case = case_cache.get(r["case_id"])
        if not case:
            return None
        conversation = build_conversation_text(case)
        golden_stl = case.get("golden_stl", "")
        t0 = time.time()
        jr = judge_evaluate(judge_llm, conversation, golden_stl, r["output"])
        elapsed = int((time.time() - t0) * 1000)
        return {
            "model": r["model"],
            "case_id": r["case_id"],
            "judge_ms": elapsed,
            "weighted_score": jr.weighted_score,
            "scores": {d: {"score": ds.score, "reason": ds.reason} for d, ds in jr.scores.items()},
            "overall_comment": jr.overall_comment,
            "parse_error": jr.parse_error,
        }

    judge_results = []
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
                    print(
                        f"  [{done}/{total}] {jr['model']:<26} {jr['case_id']:<28} "
                        f"score={jr['weighted_score']:.2f} ({jr['judge_ms']}ms)",
                        flush=True,
                    )

    judge_results.sort(key=lambda x: (x["model"], x["case_id"]))
    (OUTPUT_DIR / "quality_results.json").write_text(
        json.dumps(judge_results, ensure_ascii=False, indent=2)
    )

    # ── Phase 2 Summary ──────────────────────────────────────────────

    print(f"\n{'='*100}", flush=True)
    print("QUALITY EVALUATION SUMMARY", flush=True)
    print(f"{'='*100}", flush=True)

    model_quality = {}
    for model in MODELS:
        mr = [r for r in judge_results if r["model"] == model]
        if not mr:
            model_quality[model] = None
            continue
        ws = [r["weighted_score"] for r in mr]
        dim_avgs = {}
        for dim in DIMENSIONS:
            scores = [r["scores"][dim]["score"] for r in mr if dim in r["scores"]]
            dim_avgs[dim] = sum(scores) / len(scores) if scores else 0
        model_quality[model] = {
            "avg_weighted": sum(ws) / len(ws),
            "min_weighted": min(ws),
            "max_weighted": max(ws),
            "count": len(mr),
            "dim_avgs": dim_avgs,
        }

    # Quality table
    dim_short = {
        "completeness": "Compl",
        "predicate_choice": "Pred",
        "argument_correctness": "Args",
        "correction_handling": "Corr",
        "modifier_attachment": "Mod",
        "no_hallucination": "NoHal",
        "format_compliance": "Fmt",
    }
    print(f"\n{'Model':<28} {'Score':>6} {'Min':>5} {'Max':>5}", end="", flush=True)
    for dim in DIMENSIONS:
        print(f" {dim_short[dim]:>5}", end="")
    print(flush=True)
    print("-" * (28 + 6 + 5 + 5 + 6 * len(DIMENSIONS)), flush=True)

    ranked_models = sorted(
        [m for m in MODELS if model_quality[m]],
        key=lambda m: -model_quality[m]["avg_weighted"],
    )
    for model in ranked_models:
        mq = model_quality[model]
        print(f"{model:<28} {mq['avg_weighted']:>6.2f} {mq['min_weighted']:>5.2f} {mq['max_weighted']:>5.2f}", end="")
        for dim in DIMENSIONS:
            print(f" {mq['dim_avgs'][dim]:>5.1f}", end="")
        print(flush=True)

    # ── Combined Rankings ────────────────────────────────────────────

    print(f"\n{'='*100}", flush=True)
    print("COMBINED RANKINGS", flush=True)
    print(f"{'='*100}\n", flush=True)

    # Speed ranking
    print("1. SPEED RANKING (avg extraction ms, lower=better)", flush=True)
    for i, m in enumerate(sorted(MODELS, key=lambda m: model_stats[m]["avg_ms"] if model_stats[m]["ok"] else 999999), 1):
        s = model_stats[m]
        print(f"   {i}. {m:<28} {s['avg_ms']:>8.0f}ms (med={s['median_ms']}ms, max={s['max_ms']}ms)", flush=True)

    # Success ranking
    print(f"\n2. RELIABILITY RANKING (success rate, higher=better)", flush=True)
    for i, m in enumerate(sorted(MODELS, key=lambda m: -(model_stats[m]["ok"])), 1):
        s = model_stats[m]
        rate = s["ok"] / 20 * 100
        extra = ""
        if s["timeouts"]:
            extra += f" timeout={s['timeout_cases']}"
        if s["errors"]:
            extra += f" errors={s['error_cases']}"
        print(f"   {i}. {m:<28} {s['ok']}/20 ({rate:.0f}%){extra}", flush=True)

    # Quality ranking
    print(f"\n3. QUALITY RANKING (weighted judge score, higher=better)", flush=True)
    for i, m in enumerate(ranked_models, 1):
        mq = model_quality[m]
        print(f"   {i}. {m:<28} {mq['avg_weighted']:.2f}/10 (n={mq['count']}, range={mq['min_weighted']:.2f}-{mq['max_weighted']:.2f})", flush=True)

    # Throughput ranking
    print(f"\n4. THROUGHPUT RANKING (stmts/s, higher=better)", flush=True)
    def _tp(m):
        s = model_stats[m]
        total_s = sum(r["elapsed_ms"] for r in results if r["model"] == m and r["status"] == "ok") / 1000
        return s["total_stmts"] / total_s if total_s > 0 else 0
    for i, m in enumerate(sorted(MODELS, key=lambda m: -_tp(m)), 1):
        print(f"   {i}. {m:<28} {_tp(m):>6.2f} stmts/s", flush=True)

    # Per-dimension rankings
    print(f"\n5. PER-DIMENSION QUALITY RANKINGS", flush=True)
    for dim in DIMENSIONS:
        w = DIMENSION_WEIGHTS[dim]
        print(f"\n   [{dim}] (weight {w:.0%})", flush=True)
        for i, m in enumerate(
            sorted(
                [m for m in MODELS if model_quality[m]],
                key=lambda m: -model_quality[m]["dim_avgs"][dim],
            ),
            1,
        ):
            print(f"     {i}. {m:<28} {model_quality[m]['dim_avgs'][dim]:.1f}/10", flush=True)

    # Composite score
    print(f"\n{'='*100}", flush=True)
    print("6. COMPOSITE RANKING (speed 30% + quality 40% + reliability 20% + throughput 10%)", flush=True)
    print(f"{'='*100}", flush=True)

    active = [m for m in MODELS if model_quality[m] and model_stats[m]["ok"] > 0]
    all_avg_ms = [model_stats[m]["avg_ms"] for m in active]
    all_quality = [model_quality[m]["avg_weighted"] for m in active]
    all_tp = [_tp(m) for m in active]
    ms_min, ms_max = min(all_avg_ms), max(all_avg_ms)
    q_min, q_max = min(all_quality), max(all_quality)
    tp_min, tp_max = min(all_tp), max(all_tp)

    composite = {}
    for m in active:
        speed = 1 - (model_stats[m]["avg_ms"] - ms_min) / (ms_max - ms_min) if ms_max != ms_min else 1
        quality = (model_quality[m]["avg_weighted"] - q_min) / (q_max - q_min) if q_max != q_min else 1
        reliability = model_stats[m]["ok"] / 20
        throughput = (_tp(m) - tp_min) / (tp_max - tp_min) if tp_max != tp_min else 1
        total = speed * 0.30 + quality * 0.40 + reliability * 0.20 + throughput * 0.10
        composite[m] = {
            "total": total,
            "speed": speed,
            "quality": quality,
            "reliability": reliability,
            "throughput": throughput,
        }

    for i, (m, c) in enumerate(sorted(composite.items(), key=lambda x: -x[1]["total"]), 1):
        print(
            f"   {i}. {m:<28} {c['total']:.3f}  "
            f"(speed={c['speed']:.2f} quality={c['quality']:.2f} "
            f"reliability={c['reliability']:.2f} throughput={c['throughput']:.2f})",
            flush=True,
        )

    # ── Per-case quality breakdown ───────────────────────────────────

    case_ids = sorted(set(r["case_id"] for r in judge_results))
    print(f"\n{'='*100}", flush=True)
    print("PER-CASE QUALITY SCORES", flush=True)
    print(f"{'='*100}", flush=True)
    print(f"{'Case':<28}", end="")
    for m in ranked_models:
        print(f" {m[:12]:>12}", end="")
    print(flush=True)
    print("-" * (28 + 13 * len(ranked_models)), flush=True)
    for cid in case_ids:
        print(f"{cid:<28}", end="")
        for m in ranked_models:
            r = next((x for x in judge_results if x["model"] == m and x["case_id"] == cid), None)
            if r:
                print(f" {r['weighted_score']:>12.2f}", end="")
            else:
                print(f" {'N/A':>12}", end="")
        print(flush=True)

    # Save full report summary as JSON
    report = {
        "config": {
            "models": MODELS,
            "timeout_s": REQUEST_TIMEOUT_S,
            "judge_model": JUDGE_MODEL,
            "cases": len(case_files),
        },
        "extraction_stats": model_stats,
        "quality_stats": {m: model_quality[m] for m in MODELS if model_quality[m]},
        "composite_ranking": [
            {"rank": i + 1, "model": m, **c}
            for i, (m, c) in enumerate(sorted(composite.items(), key=lambda x: -x[1]["total"]))
        ],
    }
    (OUTPUT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\nAll results saved to: {OUTPUT_DIR}", flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
