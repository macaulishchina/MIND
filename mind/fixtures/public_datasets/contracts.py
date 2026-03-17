"""Contracts for public dataset benchmark adapters."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from mind.fixtures.episode_answer_bench import AnswerKind
from mind.kernel.contracts import ContractModel, RetrieveQueryMode
from mind.kernel.schema import validate_object


class PublicDatasetOutput(str):
    """Backward-compatible string constants for supported dataset outputs."""

    RETRIEVAL = "retrieval"
    ANSWER = "answer"
    LONG_HORIZON = "long_horizon"


class PublicDatasetDescriptor(ContractModel):
    """Metadata describing one public dataset adapter."""

    dataset_name: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supported_outputs: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_supported_outputs(self) -> PublicDatasetDescriptor:
        valid_outputs = {
            PublicDatasetOutput.RETRIEVAL,
            PublicDatasetOutput.ANSWER,
            PublicDatasetOutput.LONG_HORIZON,
        }
        invalid_outputs = [value for value in self.supported_outputs if value not in valid_outputs]
        if invalid_outputs:
            raise ValueError(f"unsupported public dataset outputs: {sorted(set(invalid_outputs))}")
        return self


class NormalizedRetrievalSpec(ContractModel):
    """Normalized retrieval benchmark case emitted by an adapter."""

    case_key: str = Field(min_length=1)
    query: str | dict[str, Any]
    query_modes: tuple[RetrieveQueryMode, ...]
    filters: dict[str, Any] = Field(default_factory=dict)
    gold_candidate_ids: tuple[str, ...]
    gold_fact_ids: tuple[str, ...]
    slot_limit: int = Field(ge=1)
    vector_scores: tuple[tuple[str, float], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_non_empty_labels(self) -> NormalizedRetrievalSpec:
        if not self.query_modes:
            raise ValueError("retrieval spec must define at least one query mode")
        if not self.gold_candidate_ids:
            raise ValueError("retrieval spec must define at least one gold candidate id")
        if not self.gold_fact_ids:
            raise ValueError("retrieval spec must define at least one gold fact id")
        return self


class NormalizedAnswerSpec(ContractModel):
    """Normalized answer benchmark case emitted by an adapter."""

    case_key: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    answer_kind: AnswerKind
    required_fragments: tuple[str, ...]
    gold_fact_ids: tuple[str, ...]
    gold_memory_refs: tuple[str, ...]
    max_answer_tokens: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_non_empty_labels(self) -> NormalizedAnswerSpec:
        if not self.required_fragments:
            raise ValueError("answer spec must define required answer fragments")
        if not self.gold_fact_ids:
            raise ValueError("answer spec must define at least one gold fact id")
        if not self.gold_memory_refs:
            raise ValueError("answer spec must define at least one gold memory ref")
        return self


class NormalizedLongHorizonStepSpec(ContractModel):
    """One normalized long-horizon step."""

    step_key: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    needed_object_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_needed_object_ids(self) -> NormalizedLongHorizonStepSpec:
        if not self.needed_object_ids:
            raise ValueError("long-horizon step must define at least one needed object id")
        return self


class NormalizedLongHorizonSequenceSpec(ContractModel):
    """Normalized long-horizon sequence emitted by an adapter."""

    sequence_key: str = Field(min_length=1)
    family: str = Field(min_length=1)
    candidate_ids: tuple[str, ...]
    steps: tuple[NormalizedLongHorizonStepSpec, ...]
    tags: tuple[str, ...] = Field(default_factory=tuple)
    maintenance_target_refs: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_candidate_ids(self) -> NormalizedLongHorizonSequenceSpec:
        if not self.candidate_ids:
            raise ValueError("long-horizon sequence must define candidate ids")
        if not self.steps:
            raise ValueError("long-horizon sequence must define at least one step")
        return self


class NormalizedEpisodeBundle(ContractModel):
    """Normalized episode-oriented bundle shared by all dataset adapters."""

    bundle_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    objects: tuple[dict[str, Any], ...]
    retrieval_specs: tuple[NormalizedRetrievalSpec, ...] = Field(default_factory=tuple)
    answer_specs: tuple[NormalizedAnswerSpec, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_objects(self) -> NormalizedEpisodeBundle:
        object_ids: list[str] = []
        for obj in self.objects:
            errors = validate_object(obj)
            if errors:
                object_id = obj.get("id", "<missing>")
                raise ValueError(
                    f"bundle {self.bundle_id} contains invalid object "
                    f"{object_id}: {errors}"
                )
            object_ids.append(str(obj["id"]))
        if len(object_ids) != len(set(object_ids)):
            raise ValueError(f"bundle {self.bundle_id} contains duplicate object ids")
        return self


class PublicDatasetFixture(ContractModel):
    """Normalized fixture set emitted by one dataset adapter."""

    descriptor: PublicDatasetDescriptor
    bundles: tuple[NormalizedEpisodeBundle, ...]
    sequence_specs: tuple[NormalizedLongHorizonSequenceSpec, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_bundle_uniqueness(self) -> PublicDatasetFixture:
        bundle_ids = [bundle.bundle_id for bundle in self.bundles]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("public dataset fixture bundle ids must be unique")
        return self

    def fixture_name(self) -> str:
        """Return the human-readable fixture name."""

        return f"{self.descriptor.dataset_name} {self.descriptor.dataset_version}"
