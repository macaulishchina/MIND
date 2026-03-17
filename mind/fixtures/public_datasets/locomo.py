"""LoCoMo public dataset adapter using a frozen in-repo sample slice."""

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
    build_reflection_note,
    build_summary_note,
    build_task_episode,
)
from mind.kernel.contracts import RetrieveQueryMode


class LoCoMoPublicDatasetAdapter:
    """Normalize a small LoCoMo-style memory slice into benchmark fixtures."""

    descriptor = PublicDatasetDescriptor(
        dataset_name="locomo",
        dataset_version="sample-v1",
        summary=(
            "Longitudinal dialogue memory slice for cross-session recall "
            "and growth evaluation."
        ),
        supported_outputs=(
            PublicDatasetOutput.RETRIEVAL,
            PublicDatasetOutput.ANSWER,
            PublicDatasetOutput.LONG_HORIZON,
        ),
    )

    def build_fixture(self) -> PublicDatasetFixture:
        """Build the normalized LoCoMo sample fixture."""

        first_bundle = _build_passport_bundle()
        second_bundle = _build_departure_bundle()
        sequence = NormalizedLongHorizonSequenceSpec(
            sequence_key="memory_trip_followup",
            family="conversation_memory",
            candidate_ids=(
                "locomo-episode-001-summary",
                "locomo-episode-001",
                "locomo-episode-001-reflection",
                "locomo-episode-002-summary",
                "locomo-episode-002",
                "locomo-episode-002-reflection",
            ),
            steps=(
                NormalizedLongHorizonStepSpec(
                    step_key="step_01",
                    task_id="locomo-task-001",
                    needed_object_ids=("locomo-episode-001-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_02",
                    task_id="locomo-task-002",
                    needed_object_ids=("locomo-episode-002-summary",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_03",
                    task_id="locomo-task-002",
                    needed_object_ids=("locomo-episode-001", "locomo-episode-002"),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_04",
                    task_id="locomo-task-002",
                    needed_object_ids=("locomo-episode-001-reflection",),
                ),
                NormalizedLongHorizonStepSpec(
                    step_key="step_05",
                    task_id="locomo-task-001+locomo-task-002",
                    needed_object_ids=(
                        "locomo-episode-001-summary",
                        "locomo-episode-002-summary",
                    ),
                ),
            ),
            tags=("public_dataset", "locomo", "memory"),
            maintenance_target_refs=(
                "locomo-episode-001-reflection",
                "locomo-episode-002-reflection",
            ),
        )
        return PublicDatasetFixture(
            descriptor=self.descriptor,
            bundles=(first_bundle, second_bundle),
            sequence_specs=(sequence,),
        )


def _build_passport_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(0)
    episode_id = "locomo-episode-001"
    task_id = "locomo-task-001"
    raw_user_id = f"{episode_id}-raw-01"
    raw_assistant_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Remember where the traveler stored the passport before the station trip.",
        result="The passport was stored in the blue desk drawer.",
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(raw_user_id, raw_assistant_id),
        source_refs=(raw_user_id, raw_assistant_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary=(
            "Before leaving for the station, the traveler stored the "
            "passport in the blue desk drawer."
        ),
        created_at=base_time + timedelta(minutes=3),
        input_refs=(raw_user_id, raw_assistant_id, episode_id),
        source_refs=(episode_id,),
    )
    reflection = build_reflection_note(
        reflection_id=f"{episode_id}-reflection",
        episode_id=episode_id,
        reflection_kind="success",
        claims=("passport location stayed stable across the follow-up question",),
        summary="Stable personal-memory fact about the passport location.",
        created_at=base_time + timedelta(minutes=4),
        source_refs=(episode_id, summary["id"]),
    )
    return NormalizedEpisodeBundle(
        bundle_id="locomo_bundle_passport",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=raw_user_id,
                episode_id=episode_id,
                record_kind="user_message",
                text="I left my passport in the blue desk drawer before heading to the station.",
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=raw_assistant_id,
                episode_id=episode_id,
                record_kind="assistant_message",
                text="Stored memory: the passport is in the blue desk drawer.",
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
            reflection,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="memory_location",
                query="Where was the passport stored before the station trip?",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(episode_id, str(summary["id"])),
                gold_fact_ids=(episode_id, str(summary["id"])),
                slot_limit=2,
            ),
            NormalizedRetrievalSpec(
                case_key="time_window_passport",
                query={
                    "start": base_time.isoformat(),
                    "end": (base_time + timedelta(minutes=3, seconds=30)).isoformat(),
                },
                query_modes=(RetrieveQueryMode.TIME_WINDOW,),
                filters={"object_types": ["RawRecord", "TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(raw_user_id, raw_assistant_id, episode_id, str(summary["id"])),
                gold_fact_ids=(raw_user_id, raw_assistant_id, episode_id),
                slot_limit=4,
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="memory_location",
                prompt="Where did the traveler store the passport before leaving for the station?",
                answer_kind=AnswerKind.TASK_RESULT,
                required_fragments=("blue desk drawer",),
                gold_fact_ids=(episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=12,
            ),
        ),
        tags=("public_dataset", "locomo", "memory"),
    )


def _build_departure_bundle() -> NormalizedEpisodeBundle:
    base_time = build_base_time(1)
    episode_id = "locomo-episode-002"
    task_id = "locomo-task-002"
    raw_user_id = f"{episode_id}-raw-01"
    raw_assistant_id = f"{episode_id}-raw-02"
    episode = build_task_episode(
        episode_id=episode_id,
        task_id=task_id,
        goal="Remember the train departure time and meeting platform.",
        result="The train leaves at 6:40 PM from platform 4 where Nora will meet the traveler.",
        success=True,
        created_at=base_time + timedelta(minutes=2),
        record_refs=(raw_user_id, raw_assistant_id),
        source_refs=(raw_user_id, raw_assistant_id),
    )
    summary = build_summary_note(
        summary_id=f"{episode_id}-summary",
        episode_id=episode_id,
        summary="The train departs at 6:40 PM from platform 4, and Nora will be waiting there.",
        created_at=base_time + timedelta(minutes=3),
        input_refs=(raw_user_id, raw_assistant_id, episode_id),
        source_refs=(episode_id,),
    )
    reflection = build_reflection_note(
        reflection_id=f"{episode_id}-reflection",
        episode_id=episode_id,
        reflection_kind="success",
        claims=("departure logistics remained consistent in the recap",),
        summary="Stable schedule memory for the station meetup.",
        created_at=base_time + timedelta(minutes=4),
        source_refs=(episode_id, summary["id"]),
    )
    return NormalizedEpisodeBundle(
        bundle_id="locomo_bundle_departure",
        task_id=task_id,
        episode_id=episode_id,
        objects=(
            build_raw_record(
                record_id=raw_user_id,
                episode_id=episode_id,
                record_kind="user_message",
                text=(
                    "Please remember that the train leaves at 6:40 PM and "
                    "Nora will meet me at platform 4."
                ),
                created_at=base_time,
                timestamp_order=1,
            ),
            build_raw_record(
                record_id=raw_assistant_id,
                episode_id=episode_id,
                record_kind="assistant_message",
                text="Stored memory: depart at 6:40 PM and meet Nora at platform 4.",
                created_at=base_time + timedelta(minutes=1),
                timestamp_order=2,
            ),
            episode,
            summary,
            reflection,
        ),
        retrieval_specs=(
            NormalizedRetrievalSpec(
                case_key="departure_plan",
                query="When does the train leave and where will Nora meet the traveler?",
                query_modes=(RetrieveQueryMode.KEYWORD,),
                filters={"object_types": ["TaskEpisode", "SummaryNote"]},
                gold_candidate_ids=(episode_id, str(summary["id"])),
                gold_fact_ids=(episode_id, str(summary["id"])),
                slot_limit=2,
            ),
        ),
        answer_specs=(
            NormalizedAnswerSpec(
                case_key="departure_plan",
                prompt="State the departure time and platform for the meetup with Nora.",
                answer_kind=AnswerKind.RESULT_AND_SUMMARY,
                required_fragments=("6:40 PM", "platform 4", "Nora"),
                gold_fact_ids=(episode_id, str(summary["id"])),
                gold_memory_refs=(episode_id, str(summary["id"])),
                max_answer_tokens=18,
            ),
        ),
        tags=("public_dataset", "locomo", "schedule"),
    )
