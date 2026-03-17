"""Tests for local-source public dataset fixture loaders."""

from __future__ import annotations

from pathlib import Path

from mind.fixtures import (
    build_public_dataset_answer_cases,
    build_public_dataset_fixture,
    build_public_dataset_long_horizon_manifest,
    build_public_dataset_retrieval_cases,
)


def test_public_dataset_fixture_can_load_locomo_from_local_source() -> None:
    """Verify LoCoMo can load a deterministic local source slice."""

    fixture = build_public_dataset_fixture("locomo", source_path=_source_path("locomo"))

    assert fixture.descriptor.dataset_name == "locomo"
    assert fixture.descriptor.dataset_version == "local-slice-v1"
    assert len(fixture.bundles) == 2
    assert fixture.bundles[0].episode_id == "locomo-local-episode-001"
    assert fixture.sequence_specs[0].sequence_key == "travel_followup_local"


def test_public_dataset_local_source_preserves_case_alignment() -> None:
    """Verify local-source retrieval and answer cases stay aligned."""

    source_path = _source_path("hotpotqa")
    retrieval_cases = build_public_dataset_retrieval_cases("hotpotqa", source_path=source_path)
    answer_cases = build_public_dataset_answer_cases("hotpotqa", source_path=source_path)

    assert {case.case_id for case in answer_cases}.issubset(
        {case.case_id for case in retrieval_cases}
    )
    assert retrieval_cases[0].case_id == "hotpotqa_hotpotqa-local-episode-001_country_of_university"


def test_public_dataset_local_source_manifest_is_deterministic() -> None:
    """Verify local-source long-horizon manifests are repeatable."""

    source_path = _source_path("scifact")
    first = build_public_dataset_long_horizon_manifest("scifact", source_path=source_path)
    second = build_public_dataset_long_horizon_manifest("scifact", source_path=source_path)

    assert first.fixture_name == "scifact local-slice-v1"
    assert first.fixture_hash == second.fixture_hash
    assert first.family_counts == (("evidence_comparison", 1),)


def test_public_dataset_local_source_missing_ref_raises_value_error(tmp_path: Path) -> None:
    """Verify local-source loaders fail clearly on unknown object refs."""

    broken_path = tmp_path / "broken.json"
    broken_path.write_text(
        (
            '{'
            '"dataset_version":"local-slice-v1",'
            '"bundles":[{'
            '"bundle_id":"broken",'
            '"task_id":"broken-task",'
            '"episode_id":"broken-episode",'
            '"day_offset":1,'
            '"goal":"g",'
            '"result":"r",'
            '"success":true,'
            '"summary":"s",'
            '"raw_records":[{"kind":"user_message","text":"hi"},{"kind":"assistant_message","text":"ok"}],'
            '"retrieval_specs":[{'
            '"case_key":"oops",'
            '"query":"q",'
            '"query_modes":["keyword"],'
            '"filters":{},'
            '"gold_candidate_refs":["missing"],'
            '"gold_fact_refs":["episode"],'
            '"slot_limit":1'
            '}],'
            '"answer_specs":[],'
            '"tags":[]'
            '}],'
            '"sequence_specs":[]'
            '}'
        ),
        encoding="utf-8",
    )

    try:
        build_public_dataset_fixture("locomo", source_path=broken_path)
    except ValueError as exc:
        assert "unknown object ref 'missing'" in str(exc)
    else:
        raise AssertionError("expected a ValueError for an unknown local source ref")


def _source_path(dataset_name: str) -> Path:
    return Path(__file__).resolve().parent / "data" / "public_datasets" / (
        f"{dataset_name}_local_slice.json"
    )