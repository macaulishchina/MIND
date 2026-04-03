from __future__ import annotations

import json
from pathlib import Path

from tests.eval.decision_opt.ab import evaluate_ab
from tests.eval.decision_opt.core import (
    DEFAULT_CASES_DIR,
    DecisionCase,
    ParsedDecision,
    build_report,
    load_cases,
    prompt_metadata,
    score_case,
)
from tests.eval.decision_opt.optimizer import (
    gate_candidate,
    replace_runtime_prompt_source,
    run_optimization_rounds,
)


class MappingDecisionLLM:
    provider = "fake"
    model = "scripted-decision"

    def __init__(self, arm: str, mapping: dict[tuple[str, str], dict[str, object]]) -> None:
        self.arm = arm
        self.mapping = mapping

    def generate(self, messages, response_format=None, temperature=None) -> str:
        system = next(m["content"] for m in messages if m["role"] == "system")
        user = next(m["content"] for m in messages if m["role"] == "user")
        key = (self.arm if "candidate" in system else self.arm, user)
        payload = self.mapping[key]
        return json.dumps(payload, ensure_ascii=False)


class AdaptiveDecisionLLM:
    provider = "fake"
    model = "adaptive-decision"

    def generate(self, messages, response_format=None, temperature=None) -> str:
        system = next(m["content"] for m in messages if m["role"] == "system")
        user = next(m["content"] for m in messages if m["role"] == "user")
        improved = "Focus this round:" in system

        if "[0] [friend:alex] attribute:favorite_music=rock" in user:
            if improved:
                payload = {
                    "action": "UPDATE",
                    "id": "0",
                    "text": "[friend:alex] attribute:favorite_music=jazz",
                    "reason": "same subject and same field",
                }
            else:
                payload = {
                    "action": "ADD",
                    "id": None,
                    "text": "[friend:alex] attribute:favorite_music=jazz",
                    "reason": "new fact",
                }
            return json.dumps(payload, ensure_ascii=False)

        if "[0] [self] attribute:favorite_snack=seaweed chips" in user:
            return json.dumps(
                {
                    "action": "NONE",
                    "id": None,
                    "text": "",
                    "reason": "already captured",
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "action": "ADD",
                "id": None,
                "text": "fallback",
                "reason": "fallback",
            },
            ensure_ascii=False,
        )


def _case_by_id(case_id: str) -> DecisionCase:
    return next(case for case in load_cases(DEFAULT_CASES_DIR) if case.id == case_id)


def test_load_decision_cases_reads_seed_dataset() -> None:
    cases = load_cases(DEFAULT_CASES_DIR)

    assert len(cases) == 12
    assert cases[0].id == "dec-001"
    assert cases[0].existing_memories[0].temp_id == "0"
    assert any(case.protected for case in cases)


def test_score_case_allows_acceptable_add_without_expected_id() -> None:
    case = _case_by_id("dec-012")
    parsed = ParsedDecision(
        action="ADD",
        id=None,
        text="[self] attribute:weekend_activity=farmer's market on Saturdays",
        reason="distinct enough to keep separately",
        parse_success=True,
    )

    score = score_case(case, parsed)

    assert score.acceptable_action_pass is True
    assert score.id_pass is True
    assert score.text_constraint_pass is True
    assert score.case_pass is True


def test_decision_ab_report_and_gate_promote_stronger_candidate() -> None:
    cases = [_case_by_id("dec-001"), _case_by_id("dec-002")]
    prompt_a = "control prompt"
    prompt_b = "candidate prompt"

    user_001 = (
        "Existing memories:\n[0] [self] attribute:favorite_snack=seaweed chips\n\n"
        "New fact: [self] attribute:favorite_snack=seaweed chips\n\n"
        "Decide what action to take.\n"
    )
    user_002 = (
        "Existing memories:\n[0] [self] attribute:favorite_snack=seaweed chips\n\n"
        "New fact: [self] attribute:favorite_snack=spicy seaweed chips\n\n"
        "Decide what action to take.\n"
    )

    control_map = {
        ("control", user_001): {"action": "NONE", "id": None, "text": "", "reason": "duplicate"},
        ("control", user_002): {
            "action": "ADD",
            "id": None,
            "text": "[self] attribute:favorite_snack=spicy seaweed chips",
            "reason": "treated as new",
        },
    }
    candidate_map = {
        ("candidate", user_001): {"action": "NONE", "id": None, "text": "", "reason": "duplicate"},
        ("candidate", user_002): {
            "action": "UPDATE",
            "id": "0",
            "text": "[self] attribute:favorite_snack=spicy seaweed chips",
            "reason": "same slot with better detail",
        },
    }

    results = evaluate_ab(
        cases=cases,
        prompt_a=prompt_a,
        prompt_b=prompt_b,
        llm_factory_a=lambda: MappingDecisionLLM("control", control_map),
        llm_factory_b=lambda: MappingDecisionLLM("candidate", candidate_map),
        prompt_label_a="control",
        prompt_label_b="candidate",
        concurrency=2,
    )
    report = build_report(
        case_results=results,
        prompt_a=prompt_metadata("control", prompt_a, "scripted"),
        prompt_b=prompt_metadata("candidate", prompt_b, "scripted"),
    )
    gate = gate_candidate(report)

    assert report["summary"]["arm_a"]["case_pass_rate"] == 0.5
    assert report["summary"]["arm_b"]["case_pass_rate"] == 1.0
    assert gate.promote is True
    assert gate.reasons == []


def test_run_optimization_rounds_promotes_heuristic_candidate(tmp_path: Path) -> None:
    cases = [_case_by_id("dec-001"), _case_by_id("dec-006")]

    summary = run_optimization_rounds(
        cases=cases,
        control_prompt="minimal runtime prompt",
        llm_factory=lambda: AdaptiveDecisionLLM(),
        prompt_label="runtime-control",
        rounds=1,
        artifacts_dir=tmp_path,
        concurrency=1,
    )

    assert (tmp_path / "baseline_report.json").exists()
    assert (tmp_path / "round_01_candidate_prompt.txt").exists()
    assert (tmp_path / "round_01_report.json").exists()
    assert (tmp_path / "round_01_gate.json").exists()
    assert summary["baseline_summary"]["case_pass_rate"] == 0.5
    assert summary["final_summary"]["case_pass_rate"] == 1.0


def test_replace_runtime_prompt_source_updates_only_decision_prompt() -> None:
    source = """\
UPDATE_DECISION_SYSTEM_PROMPT = \"\"\"\\
old prompt
\"\"\"

OTHER_PROMPT = \"\"\"\\
keep me
\"\"\"
"""
    updated = replace_runtime_prompt_source(source, "new prompt body")

    assert 'UPDATE_DECISION_SYSTEM_PROMPT = """\\\nnew prompt body\n"""' in updated
    assert 'OTHER_PROMPT = """\\\nkeep me\n"""' in updated

