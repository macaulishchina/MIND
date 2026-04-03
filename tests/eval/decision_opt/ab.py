"""A/B execution helpers for decision prompt evaluation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from tests.eval.decision_opt import judge as decision_judge
from tests.eval.decision_opt.core import (
    DecisionABCaseResult,
    DecisionArmResult,
    DecisionCase,
    attach_judge_score,
    compare_case,
    run_arm,
)


def evaluate_case_pair(
    case: DecisionCase,
    prompt_a: str,
    prompt_b: str,
    llm_a,
    llm_b,
    prompt_label_a: str,
    prompt_label_b: str,
    judge_llm=None,
) -> DecisionABCaseResult:
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(run_arm, case, prompt_a, llm_a, "A", prompt_label_a)
        fut_b = pool.submit(run_arm, case, prompt_b, llm_b, "B", prompt_label_b)
        arm_a = fut_a.result()
        arm_b = fut_b.result()

    if judge_llm is not None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_judge_a = pool.submit(decision_judge.evaluate, judge_llm, case, arm_a)
            fut_judge_b = pool.submit(decision_judge.evaluate, judge_llm, case, arm_b)
            judge_a = fut_judge_a.result()
            judge_b = fut_judge_b.result()
        arm_a = attach_judge_score(
            result=arm_a,
            case=case,
            judge_weighted_score=judge_a.weighted_score,
            judge_details={
                "scores": judge_a.scores,
                "overall_comment": judge_a.overall_comment,
                "parse_error": judge_a.parse_error,
            },
        )
        arm_b = attach_judge_score(
            result=arm_b,
            case=case,
            judge_weighted_score=judge_b.weighted_score,
            judge_details={
                "scores": judge_b.scores,
                "overall_comment": judge_b.overall_comment,
                "parse_error": judge_b.parse_error,
            },
        )

    return compare_case(case, arm_a, arm_b)


def evaluate_single_case(
    case: DecisionCase,
    prompt_text: str,
    llm,
    prompt_label: str,
    judge_llm=None,
) -> DecisionArmResult:
    result = run_arm(case, prompt_text, llm, "A", prompt_label)
    if judge_llm is None:
        return result
    judged = decision_judge.evaluate(judge_llm, case, result)
    return attach_judge_score(
        result=result,
        case=case,
        judge_weighted_score=judged.weighted_score,
        judge_details={
            "scores": judged.scores,
            "overall_comment": judged.overall_comment,
            "parse_error": judged.parse_error,
        },
    )


def evaluate_ab(
    cases: list[DecisionCase],
    prompt_a: str,
    prompt_b: str,
    llm_factory_a: Callable[[], object],
    llm_factory_b: Callable[[], object],
    prompt_label_a: str,
    prompt_label_b: str,
    judge_factory: Callable[[], object] | None = None,
    concurrency: int = 4,
) -> list[DecisionABCaseResult]:
    if concurrency <= 1:
        return [
            evaluate_case_pair(
                case=case,
                prompt_a=prompt_a,
                prompt_b=prompt_b,
                llm_a=llm_factory_a(),
                llm_b=llm_factory_b(),
                prompt_label_a=prompt_label_a,
                prompt_label_b=prompt_label_b,
                judge_llm=judge_factory() if judge_factory is not None else None,
            )
            for case in cases
        ]

    ordered: list[DecisionABCaseResult | None] = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_map = {
            pool.submit(
                evaluate_case_pair,
                case,
                prompt_a,
                prompt_b,
                llm_factory_a(),
                llm_factory_b(),
                prompt_label_a,
                prompt_label_b,
                judge_factory() if judge_factory is not None else None,
            ): idx
            for idx, case in enumerate(cases)
        }
        for future in as_completed(future_map):
            ordered[future_map[future]] = future.result()
    return [item for item in ordered if item is not None]


def evaluate_single_prompt(
    cases: list[DecisionCase],
    prompt_text: str,
    llm_factory: Callable[[], object],
    prompt_label: str,
    judge_factory: Callable[[], object] | None = None,
    concurrency: int = 4,
) -> list[DecisionArmResult]:
    if concurrency <= 1:
        return [
            evaluate_single_case(
                case=case,
                prompt_text=prompt_text,
                llm=llm_factory(),
                prompt_label=prompt_label,
                judge_llm=judge_factory() if judge_factory is not None else None,
            )
            for case in cases
        ]

    ordered: list[DecisionArmResult | None] = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_map = {
            pool.submit(
                evaluate_single_case,
                case,
                prompt_text,
                llm_factory(),
                prompt_label,
                judge_factory() if judge_factory is not None else None,
            ): idx
            for idx, case in enumerate(cases)
        }
        for future in as_completed(future_map):
            ordered[future_map[future]] = future.result()
    return [item for item in ordered if item is not None]


def arms_from_cases(case_results: list[DecisionABCaseResult]) -> tuple[list[DecisionArmResult], list[DecisionArmResult]]:
    return ([case.arm_a for case in case_results], [case.arm_b for case in case_results])
