"""Tests for public dataset benchmark adapters."""

from __future__ import annotations

from mind.fixtures import (
    build_public_dataset_answer_cases,
    build_public_dataset_fixture,
    build_public_dataset_long_horizon_manifest,
    build_public_dataset_long_horizon_sequences,
    build_public_dataset_objects,
    build_public_dataset_retrieval_cases,
    get_public_dataset_adapter,
    list_public_dataset_descriptors,
)
from mind.fixtures.public_datasets.registry import UnknownPublicDatasetError
from mind.kernel.contracts import RetrieveQueryMode
from mind.kernel.schema import validate_object


def test_public_dataset_registry_exposes_expected_adapters() -> None:
    """Verify the registered public dataset adapters are stable."""

    descriptors = list_public_dataset_descriptors()

    assert tuple(descriptor.dataset_name for descriptor in descriptors) == (
        "hotpotqa",
        "locomo",
        "scifact",
    )
    assert all(descriptor.dataset_version == "sample-v1" for descriptor in descriptors)


def test_public_dataset_fixture_objects_are_schema_valid() -> None:
    """Verify compiled public dataset objects satisfy the kernel schema."""

    for dataset_name in ("locomo", "hotpotqa", "scifact"):
        objects = build_public_dataset_objects(dataset_name)
        assert objects, f"expected objects for {dataset_name}"
        for obj in objects:
            assert validate_object(obj) == []


def test_public_dataset_retrieval_and_answer_cases_share_case_ids() -> None:
    """Verify retrieval and answer cases stay aligned by case id."""

    for dataset_name in ("locomo", "hotpotqa", "scifact"):
        retrieval_cases = build_public_dataset_retrieval_cases(dataset_name)
        answer_cases = build_public_dataset_answer_cases(dataset_name)
        retrieval_case_ids = {case.case_id for case in retrieval_cases}
        answer_case_ids = {case.case_id for case in answer_cases}

        assert retrieval_case_ids
        assert answer_case_ids
        assert answer_case_ids.issubset(retrieval_case_ids)


def test_public_dataset_modes_cover_keyword_time_and_vector() -> None:
    """Verify the initial adapters exercise multiple retrieval query modes."""

    locomo_cases = build_public_dataset_retrieval_cases("locomo")
    scifact_cases = build_public_dataset_retrieval_cases("scifact")

    assert any(RetrieveQueryMode.TIME_WINDOW in case.query_modes for case in locomo_cases)
    assert any(RetrieveQueryMode.VECTOR in case.query_modes for case in scifact_cases)
    combined_cases = [*locomo_cases, *scifact_cases]
    assert any(RetrieveQueryMode.KEYWORD in case.query_modes for case in combined_cases)


def test_public_dataset_long_horizon_manifest_is_stable() -> None:
    """Verify public dataset long-horizon manifests are deterministic."""

    manifest = build_public_dataset_long_horizon_manifest("locomo")
    sequences = build_public_dataset_long_horizon_sequences("locomo")

    assert manifest.fixture_name == "locomo sample-v1"
    assert manifest.sequence_count == 1
    assert manifest.min_step_count == 5
    assert manifest.max_step_count == 5
    assert len(manifest.fixture_hash) == 64
    assert manifest.family_counts == (("conversation_memory", 1),)
    assert len(sequences) == 1
    assert sequences[0].sequence_id == "locomo_memory_trip_followup"


def test_unknown_public_dataset_adapter_raises_error() -> None:
    """Verify unknown public dataset lookups fail clearly."""

    try:
        get_public_dataset_adapter("unknown-dataset")
    except UnknownPublicDatasetError as exc:
        assert "unknown public dataset adapter" in str(exc)
    else:
        raise AssertionError("expected UnknownPublicDatasetError")


def test_public_dataset_fixture_descriptor_matches_registry() -> None:
    """Verify fixture descriptors match the registry metadata."""

    fixture = build_public_dataset_fixture("hotpotqa")
    adapter = get_public_dataset_adapter("hotpotqa")

    assert fixture.descriptor == adapter.descriptor
    assert fixture.fixture_name() == "hotpotqa sample-v1"
