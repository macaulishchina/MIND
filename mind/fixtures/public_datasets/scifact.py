"""SciFact public dataset adapter using a frozen in-repo sample slice."""

from __future__ import annotations

from datetime import timedelta

from mind.fixtures.episode_answer_bench import AnswerKind
from mind.fixtures.public_datasets.contracts import (
    NormalizedAnswerSpec,
    NormalizedEpisodeBundle,
    NormalizedLongHorizonSequenceSpec,
    NormalizedLongHorizonStepSpec,
    NormalizedRetrievalSpec,
    PublicDatasetDescriptor,
    PublicDatasetFixture,
    PublicDatasetOutput,
)
from mind.fixtures.public_datasets.object_factory import (
    build_base_time,
    build_raw_record,
    build_summary_note,
    build_task_episode,
)
from mind.kernel.contracts import RetrieveQueryMode


class SciFactPublicDatasetAdapter:
    """Normalize a small SciFact-style evidence slice into benchmark fixtures."""

    descriptor = PublicDatasetDescriptor(
        dataset_name="scifact",
        dataset_version="sample-v1",
        summary=(
            "Evidence-grounded scientific claim slice for retrieval "
            "calibration and verdict answers."
        ),
        supported_outputs=(
            PublicDatasetOutput.RETRIEVAL,
            PublicDatasetOutput.ANSWER,
            PublicDatasetOutput.LONG_HORIZON,
        ),
    )

    def build_fixture(self) -> PublicDatasetFixture:
        """Build the normalized SciFact sample fixture."""

        first_bundle = _build_sleep_bundle()
        second_bundle = _build_vitamin_bundle()
        sequence = NormalizedLongHorizonSequenceSpec(
            sequence_key="claim_review_sequence",
            family="evidence_comparison",
            candidate_ids=(
                "scifact-episode-001-summary",
                "scifact-episode-001",
                "scifact-episode-002-summary",
                "scifact-episode-002",
                "scifact-episode-001-raw-02",
                "scifact-episode-002-raw-02",
            ),
            steps=(
                NormalizedLongHorizonStepSpec(
                    step_key="step_01",
                    task_id="scifact-task-001",
                    needed_object_ids=("scifact-episode-001-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_02",
                    task_id="scifact-task-002",
                    needed_object_ids=("scifact-episode-002-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_03",
                    task_id="scifact-task-001+scifact-task-002",
                    needed_object_ids=("scifact-episode-001", "scifact-episode-002"),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_04",
                    task_id="scifact-task-001+scifact-task-002",
                    needed_object_ids=(
                        "scifact-episode-001-raw-02",
                        "scifact-episode-002-raw-02",
                    ),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_05",
                    task_id="scifact-task-001+scifact-task-002",
                    needed_object_ids=(
                        "scifact-episode-001-summary",
                        "scifact-episode-002-summary",
                    ),
                ),
            ),
            tags=("public_dataset", "scifact", "evidence"),
        )
        return PublicDatasetFixture(
            descriptor=self.descriptor,
            bundles=(first_bundle, second_bundle),
            sequence_specs=(sequence,),
        )


def _build_sleep_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(20)
    episode_id = "scifact-episode-001"
    task_id = "scifact-task-001"
    claim_id = f"{episode_id}-raw-01"
    evidence_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Assess whether moderate exercise improves sleep quality in older adults.",
        result=(
            "Supported: the cited evidence indicates moderate exercise "
            "improves sleep quality in older adults."
        ),
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(claim_id, evidence_id),
        source_refs=(claim_id, evidence_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary=(
            "The claim is supported because the evidence links moderate "
            "exercise to better sleep quality in older adults."
        ),
        created_at=base_time + timedelta(minutes=3),
        input_refs=(claim_id, evidence_id, episode_id),
        source_refs=(episode_id,),
    )
    return NormalizedEpisodeBundle(
        bundle_id="scifact_bundle_sleep",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=claim_id,
                episode_id=episode_id,
                record_kind="user_message",
                text="Claim: moderate exercise improves sleep quality in older adults.",
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=evidence_id,
                episode_id=episode_id,
                record_kind="tool_result",
                text=(
                    "Evidence abstract: older adults who followed moderate "
                    "exercise routines showed improved sleep quality metrics."
                ),
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="sleep_claim_keyword",
                query="moderate exercise improves sleep quality in older adults",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["RawRecord", "TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(claim_id, evidence_id, episode_id, str(summary["id"])),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                slot_limit=4,
            ),
            NormalizedRetrievalSpec(
                case_key="sleep_claim_vector",
                query="vector:scifact-sleep-claim",
                query_modes=(RetrieveQueryMode.VECTOR,),
                filters={"object_types": ["SummaryNote", "TaskEpisode"]},
                gold_candidate_ids=(str(summary["id"]), episode_id),
                gold_fact_ids=(str(summary["id"]), episode_id),
                slot_limit=2,
                vector_scores=((str(summary["id"]), 0.97), (episode_id, 0.93)),
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="sleep_claim_keyword",
                prompt="What is the verdict for the exercise-and-sleep claim?",
                answer_kind=AnswerKind.TASK_RESULT,
                required_fragments=("Supported", "exercise", "sleep quality"),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=16,
            ),
        ),
        tags=("public_dataset", "scifact", "supported"),
    )


def _build_vitamin_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(21)
    episode_id = "scifact-episode-002"
    task_id = "scifact-task-002"
    claim_id = f"{episode_id}-raw-01"
    evidence_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Assess whether daily vitamin C prevents every seasonal cold.",
        result=(
            "Refuted: the evidence does not show that daily vitamin C "
            "prevents every seasonal cold."
        ),
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(claim_id, evidence_id),
        source_refs=(claim_id, evidence_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary=(
            "The claim is refuted because the evidence does not support "
            "universal cold prevention from daily vitamin C."
        ),
        created_at=base_time + timedelta(minutes=3),
        input_refs=(claim_id, evidence_id, episode_id),
        source_refs=(episode_id,),
    )
    return NormalizedEpisodeBundle(
        bundle_id="scifact_bundle_vitamin",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=claim_id,
                episode_id=episode_id,
                record_kind="user_message",
                text="Claim: taking vitamin C every day prevents every seasonal cold.",
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=evidence_id,
                episode_id=episode_id,
                record_kind="tool_result",
                text=(
                    "Evidence abstract: daily vitamin C may reduce duration "
                    "for some people, but it does not prevent every seasonal "
                    "cold."
                ),
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="vitamin_claim_keyword",
                query="daily vitamin C prevents every seasonal cold",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["RawRecord", "TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(claim_id, evidence_id, episode_id, str(summary["id"])),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                slot_limit=4,
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="vitamin_claim_keyword",
                prompt="What is the verdict for the vitamin C claim?",
                answer_kind=AnswerKind.TASK_RESULT,
                required_fragments=("Refuted", "vitamin C", "seasonal cold"),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=16,
            ),
        ),
        tags=("public_dataset", "scifact", "refuted"),
    )
