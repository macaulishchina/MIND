"""HotpotQA public dataset adapter using a frozen in-repo sample slice."""

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


class HotpotQAPublicDatasetAdapter:
    """Normalize a small HotpotQA-style multi-hop slice into benchmark fixtures."""

    descriptor = PublicDatasetDescriptor(
        dataset_name="hotpotqa",
        dataset_version="sample-v1",
        summary=(
            "Multi-hop QA slice with explicit supporting facts for "
            "retrieval and answer checks."
        ),
        supported_outputs=(
            PublicDatasetOutput.RETRIEVAL,
            PublicDatasetOutput.ANSWER,
            PublicDatasetOutput.LONG_HORIZON,
        ),
    )

    def build_fixture(self) -> PublicDatasetFixture:
        """Build the normalized HotpotQA sample fixture."""

        first_bundle = _build_hobbit_bundle()
        second_bundle = _build_curie_bundle()
        sequence = NormalizedLongHorizonSequenceSpec(
            sequence_key="evidence_chain_review",
            family="multi_hop_reasoning",
            candidate_ids=(
                "hotpotqa-episode-001-summary",
                "hotpotqa-episode-001",
                "hotpotqa-episode-002-summary",
                "hotpotqa-episode-002",
                "hotpotqa-episode-001-raw-01",
                "hotpotqa-episode-002-raw-01",
            ),
            steps=(
                NormalizedLongHorizonStepSpec(
                    step_key="step_01",
                    task_id="hotpot-task-001",
                    needed_object_ids=("hotpotqa-episode-001-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_02",
                    task_id="hotpot-task-002",
                    needed_object_ids=("hotpotqa-episode-002-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_03",
                    task_id="hotpot-task-001+hotpot-task-002",
                    needed_object_ids=("hotpotqa-episode-001", "hotpotqa-episode-002"),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_04",
                    task_id="hotpot-task-001+hotpot-task-002",
                    needed_object_ids=(
                        "hotpotqa-episode-001-raw-01",
                        "hotpotqa-episode-002-raw-01",
                    ),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_05",
                    task_id="hotpot-task-001+hotpot-task-002",
                    needed_object_ids=(
                        "hotpotqa-episode-001-summary",
                        "hotpotqa-episode-002-summary",
                    ),
                ),
            ),
            tags=("public_dataset", "hotpotqa", "multi_hop"),
        )
        return PublicDatasetFixture(
            descriptor=self.descriptor,
            bundles=(first_bundle, second_bundle),
            sequence_specs=(sequence,),
        )


def _build_hobbit_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(10)
    episode_id = "hotpotqa-episode-001"
    task_id = "hotpot-task-001"
    question_id = f"{episode_id}-raw-01"
    evidence_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Answer a multi-hop question about where the author of The Hobbit studied.",
        result="The author of The Hobbit studied at Oxford, which is in England.",
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(question_id, evidence_id),
        source_refs=(question_id, evidence_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary="Tolkien studied at Oxford, and Oxford is located in England.",
        created_at=base_time + timedelta(minutes=3),
        input_refs=(question_id, evidence_id, episode_id),
        source_refs=(episode_id,),
    )
    return NormalizedEpisodeBundle(
        bundle_id="hotpotqa_bundle_hobbit",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=question_id,
                episode_id=episode_id,
                record_kind="user_message",
                text="In which country is the university attended by the author of The Hobbit?",
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=evidence_id,
                episode_id=episode_id,
                record_kind="tool_result",
                text="Supporting facts: Tolkien studied at Oxford; Oxford is in England.",
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="country_of_university",
                query="Which country contains the university attended by the author of The Hobbit?",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["RawRecord", "TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(question_id, evidence_id, episode_id, str(summary["id"])),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                slot_limit=4,
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="country_of_university",
                prompt=(
                    "Answer the multi-hop question about the country of the "
                    "university attended by The Hobbit's author."
                ),
                answer_kind=AnswerKind.RESULT_AND_SUMMARY,
                required_fragments=("England", "Oxford", "Tolkien"),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=18,
            ),
        ),
        tags=("public_dataset", "hotpotqa", "multi_hop"),
    )


def _build_curie_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(11)
    episode_id = "hotpotqa-episode-002"
    task_id = "hotpot-task-002"
    question_id = f"{episode_id}-raw-01"
    evidence_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Answer a multi-hop question about the city linked to Marie Curie.",
        result="Marie Curie taught at the University of Paris, which is in Paris.",
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(question_id, evidence_id),
        source_refs=(question_id, evidence_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary="Marie Curie taught at the University of Paris, so the linked city is Paris.",
        created_at=base_time + timedelta(minutes=3),
        input_refs=(question_id, evidence_id, episode_id),
        source_refs=(episode_id,),
    )
    return NormalizedEpisodeBundle(
        bundle_id="hotpotqa_bundle_curie",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=question_id,
                episode_id=episode_id,
                record_kind="user_message",
                text="Which city is associated with the university where Marie Curie taught?",
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=evidence_id,
                episode_id=episode_id,
                record_kind="tool_result",
                text=(
                    "Supporting facts: Marie Curie taught at the University "
                    "of Paris; the university is in Paris."
                ),
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="city_of_university",
                query="Which city is tied to the university where Marie Curie taught?",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["RawRecord", "TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(question_id, evidence_id, episode_id, str(summary["id"])),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                slot_limit=4,
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="city_of_university",
                prompt=(
                    "Answer the multi-hop question about the city linked to "
                    "Marie Curie's university."
                ),
                answer_kind=AnswerKind.RESULT_AND_SUMMARY,
                required_fragments=("Paris", "University of Paris", "Marie Curie"),
                gold_fact_ids=(evidence_id, episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=18,
            ),
        ),
        tags=("public_dataset", "hotpotqa", "comparison"),
    )
