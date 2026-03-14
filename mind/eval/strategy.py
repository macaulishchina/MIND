"""Strategy primitives for optimization work."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

from mind.fixtures.long_horizon_dev import LongHorizonStep
from mind.fixtures.long_horizon_eval import LongHorizonEvalSequence
from mind.kernel.store import SQLiteMemoryStore


@dataclass(frozen=True)
class StrategyStepDecision:
    """A single step-level memory selection decision."""

    budget: int
    prefer_future_coverage: bool
    allow_schema_expansion: bool
    selected_ids: tuple[str, ...]


class MindStrategy(ABC):
    """Interface implemented by fixed-rule and optimized strategies."""

    strategy_id = "abstract"

    @abstractmethod
    def select_step_handles(
        self,
        *,
        store: SQLiteMemoryStore,
        sequence: LongHorizonEvalSequence,
        step_index: int,
        step: LongHorizonStep,
        candidate_ids: tuple[str, ...],
        ranking_by_id: Mapping[str, float],
    ) -> StrategyStepDecision: ...


@dataclass(frozen=True)
class FixedRuleMindStrategy(MindStrategy):
    """The frozen fixed-rule strategy baseline used as the optimization anchor."""

    strategy_id = "fixed_rule_v1"
    step_budget: int = 1
    prefer_future_coverage: bool = True
    allow_schema_expansion: bool = True

    def select_step_handles(
        self,
        *,
        store: SQLiteMemoryStore,
        sequence: LongHorizonEvalSequence,
        step_index: int,
        step: LongHorizonStep,
        candidate_ids: tuple[str, ...],
        ranking_by_id: Mapping[str, float],
    ) -> StrategyStepDecision:
        selected_ids = select_step_handles(
            store,
            candidate_ids,
            step.needed_object_ids,
            ranking_by_id,
            budget=self.step_budget,
            future_steps=sequence.steps[step_index:],
            prefer_future_coverage=self.prefer_future_coverage,
            allow_schema_expansion=self.allow_schema_expansion,
        )
        return StrategyStepDecision(
            budget=self.step_budget,
            prefer_future_coverage=self.prefer_future_coverage,
            allow_schema_expansion=self.allow_schema_expansion,
            selected_ids=selected_ids,
        )


@dataclass(frozen=True)
class OptimizedMindStrategy(MindStrategy):
    """Budget-preserving heuristic strategy used as the first optimizer."""

    strategy_id = "optimized_v1"
    base_step_budget: int = 1
    prefer_future_coverage: bool = True
    allow_schema_expansion: bool = True
    direct_need_bonus: float = 0.03

    def select_step_handles(
        self,
        *,
        store: SQLiteMemoryStore,
        sequence: LongHorizonEvalSequence,
        step_index: int,
        step: LongHorizonStep,
        candidate_ids: tuple[str, ...],
        ranking_by_id: Mapping[str, float],
    ) -> StrategyStepDecision:
        budget_schedule = optimized_budget_schedule(
            sequence=sequence,
            candidate_ids=candidate_ids,
            base_step_budget=self.base_step_budget,
        )
        budget = budget_schedule[step_index]
        if budget <= 0:
            return StrategyStepDecision(
                budget=0,
                prefer_future_coverage=self.prefer_future_coverage,
                allow_schema_expansion=self.allow_schema_expansion,
                selected_ids=(),
            )
        selected_ids = select_step_handles(
            store,
            candidate_ids,
            step.needed_object_ids,
            ranking_by_id,
            budget=budget,
            future_steps=sequence.steps[step_index:],
            prefer_future_coverage=self.prefer_future_coverage,
            allow_schema_expansion=self.allow_schema_expansion,
            object_bonus_by_id=needed_object_bonus(
                step.needed_object_ids,
                direct_need_bonus=self.direct_need_bonus,
            ),
        )
        return StrategyStepDecision(
            budget=budget,
            prefer_future_coverage=self.prefer_future_coverage,
            allow_schema_expansion=self.allow_schema_expansion,
            selected_ids=selected_ids,
        )


def select_step_handles(
    store: SQLiteMemoryStore,
    candidate_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
    ranking_by_id: Mapping[str, float],
    *,
    budget: int,
    future_steps: tuple[LongHorizonStep, ...],
    prefer_future_coverage: bool,
    allow_schema_expansion: bool,
    object_bonus_by_id: Mapping[str, float] | None = None,
) -> tuple[str, ...]:
    selected: list[str] = []
    uncovered = set(needed_object_ids)
    candidate_bonus = object_bonus_by_id or {}

    for _ in range(budget):
        best_id: str | None = None
        best_key: tuple[float, float, float, float, float, str] | None = None
        for object_id in candidate_ids:
            if object_id in selected:
                continue
            coverage = handle_coverage(
                store,
                object_id,
                allow_schema_expansion=allow_schema_expansion,
            )
            new_hits = len(coverage.intersection(uncovered))
            total_hits = len(coverage.intersection(needed_object_ids))
            future_hits = (
                future_coverage_hits(
                    store,
                    object_id,
                    future_steps,
                    allow_schema_expansion=allow_schema_expansion,
                )
                if prefer_future_coverage
                else 0
            )
            key = (
                float(new_hits),
                float(total_hits),
                float(candidate_bonus.get(object_id, 0.0)),
                float(future_hits),
                float(ranking_by_id.get(object_id, 0.0)),
                object_id,
            )
            if best_key is None or key > best_key:
                best_key = key
                best_id = object_id
        if best_id is None:
            break
        selected.append(best_id)
        uncovered.difference_update(
            handle_coverage(
                store,
                best_id,
                allow_schema_expansion=allow_schema_expansion,
            )
        )
        if not uncovered:
            break

    return tuple(selected)


def handle_coverage(
    store: SQLiteMemoryStore,
    object_id: str,
    *,
    allow_schema_expansion: bool,
) -> set[str]:
    obj = store.read_object(object_id)
    coverage = {object_id}
    metadata = obj.get("metadata", {})
    if allow_schema_expansion and obj["type"] == "SchemaNote":
        refs = metadata.get("promotion_source_refs") or metadata.get("evidence_refs") or []
        coverage.update(str(ref) for ref in refs)
    return coverage


def covered_needed_ids(
    store: SQLiteMemoryStore,
    selected_ids: tuple[str, ...],
    needed_object_ids: tuple[str, ...],
    *,
    allow_schema_expansion: bool,
) -> set[str]:
    covered: set[str] = set()
    needed = set(needed_object_ids)
    for object_id in selected_ids:
        covered.update(
            handle_coverage(
                store,
                object_id,
                allow_schema_expansion=allow_schema_expansion,
            ).intersection(needed)
        )
    return covered


def future_coverage_hits(
    store: SQLiteMemoryStore,
    object_id: str,
    future_steps: tuple[LongHorizonStep, ...],
    *,
    allow_schema_expansion: bool,
) -> int:
    coverage = handle_coverage(
        store,
        object_id,
        allow_schema_expansion=allow_schema_expansion,
    )
    return sum(len(coverage.intersection(step.needed_object_ids)) for step in future_steps)


def optimized_budget_schedule(
    *,
    sequence: LongHorizonEvalSequence,
    candidate_ids: tuple[str, ...],
    base_step_budget: int,
) -> tuple[int, ...]:
    budgets = [base_step_budget for _ in sequence.steps]
    if not budgets:
        return ()
    donor_index = len(budgets) - 1
    target_index = first_completable_multi_object_step(sequence, candidate_ids)
    if target_index is not None and target_index != donor_index and budgets[donor_index] > 0:
        budgets[target_index] += 1
        budgets[donor_index] -= 1
    return tuple(budgets)


def first_completable_multi_object_step(
    sequence: LongHorizonEvalSequence,
    candidate_ids: tuple[str, ...],
) -> int | None:
    available_ids = set(candidate_ids)
    for step_index, step in enumerate(sequence.steps[:-1]):
        if len(step.needed_object_ids) < 2:
            continue
        if all(object_id in available_ids for object_id in step.needed_object_ids):
            return step_index
    return None


def needed_object_bonus(
    needed_object_ids: tuple[str, ...],
    *,
    direct_need_bonus: float,
) -> dict[str, float]:
    return {
        object_id: round(direct_need_bonus - (index * 0.01), 4)
        for index, object_id in enumerate(needed_object_ids)
        if direct_need_bonus - (index * 0.01) > 0.0
    }
