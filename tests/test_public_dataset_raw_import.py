"""Tests for compiling raw public-dataset inputs into local slices."""

from __future__ import annotations

import json
from pathlib import Path

from mind.fixtures import (
    build_public_dataset_fixture,
    compile_public_dataset_local_slice,
    write_public_dataset_local_slice_json,
)


def test_compile_scifact_raw_input_to_local_slice_round_trips_through_loader(
    tmp_path: Path,
) -> None:
    """Verify raw SciFact JSONL inputs compile into a loadable normalized slice."""

    payload = compile_public_dataset_local_slice(
        "scifact",
        _raw_source_path(),
        claim_ids=(101, 102),
    )
    output_path = write_public_dataset_local_slice_json(tmp_path / "scifact_slice.json", payload)
    fixture = build_public_dataset_fixture("scifact", source_path=output_path)
    bundles = payload["bundles"]
    assert isinstance(bundles, list)

    assert payload["dataset_version"] == "raw-slice-v1"
    assert len(bundles) == 2
    assert fixture.descriptor.dataset_version == "raw-slice-v1"
    assert fixture.bundles[0].episode_id == "scifact-raw-episode-101"
    assert fixture.sequence_specs[0].family == "evidence_comparison"


def test_compile_scifact_raw_input_respects_max_items_and_skips_unsupported_labels() -> None:
    """Verify raw import selects only supported/refuted claims by default."""

    payload = compile_public_dataset_local_slice(
        "scifact",
        _raw_source_path(),
        max_items=1,
    )

    bundles = payload["bundles"]
    assert isinstance(bundles, list)
    assert len(bundles) == 1
    first_bundle = bundles[0]
    assert isinstance(first_bundle, dict)
    assert first_bundle["episode_id"] == "scifact-raw-episode-101"


def test_compile_scifact_raw_input_raises_for_missing_corpus_doc(tmp_path: Path) -> None:
    """Verify raw import fails clearly when evidence points to a missing corpus doc."""

    source_dir = tmp_path / "scifact_raw"
    source_dir.mkdir(parents=True)
    (source_dir / "claims.jsonl").write_text(
        (
            '{"id": 201, "claim": "Exercise helps balance.", "label": "SUPPORT", '
            '"evidence": {"99": [{"sentences": [0], "label": "SUPPORT"}]}}\n'
        ),
        encoding="utf-8",
    )
    (source_dir / "corpus.jsonl").write_text(
        (
            '{"doc_id": 1, "title": "Exercise", "abstract": ["Exercise can improve balance."]}\n'
        ),
        encoding="utf-8",
    )

    try:
        compile_public_dataset_local_slice("scifact", source_dir)
    except ValueError as exc:
        assert "missing corpus doc_id 99" in str(exc)
    else:
        raise AssertionError("expected a ValueError for a missing SciFact corpus doc")


def test_write_public_dataset_local_slice_json_persists_payload(tmp_path: Path) -> None:
    """Verify compiled local-slice payloads can be persisted as JSON."""

    payload = compile_public_dataset_local_slice("scifact", _raw_source_path(), max_items=1)
    output_path = write_public_dataset_local_slice_json(tmp_path / "slice.json", payload)
    round_trip = json.loads(output_path.read_text(encoding="utf-8"))

    assert round_trip["dataset_version"] == "raw-slice-v1"
    assert len(round_trip["bundles"]) == 1


def test_compile_hotpotqa_raw_input_to_local_slice_round_trips_through_loader(
    tmp_path: Path,
) -> None:
    """Verify raw HotpotQA examples compile into a loadable normalized slice."""

    payload = compile_public_dataset_local_slice(
        "hotpotqa",
        _hotpotqa_raw_source_path(),
        example_ids=("5a8b57f25542995d1e6f1371", "5a7a06935542990198eaf050"),
    )
    output_path = write_public_dataset_local_slice_json(tmp_path / "hotpotqa_slice.json", payload)
    fixture = build_public_dataset_fixture("hotpotqa", source_path=output_path)
    bundles = payload["bundles"]
    assert isinstance(bundles, list)

    assert payload["dataset_version"] == "raw-slice-v1"
    assert len(bundles) == 2
    assert fixture.descriptor.dataset_version == "raw-slice-v1"
    assert fixture.bundles[0].episode_id == "hotpotqa-raw-episode-5a8b57f25542995d1e6f1371"
    assert fixture.sequence_specs[0].family == "multi_hop_reasoning"


def test_compile_hotpotqa_raw_input_respects_max_items() -> None:
    """Verify raw HotpotQA import can compile a bounded example set."""

    payload = compile_public_dataset_local_slice(
        "hotpotqa",
        _hotpotqa_raw_source_path(),
        max_items=1,
    )

    bundles = payload["bundles"]
    assert isinstance(bundles, list)
    assert len(bundles) == 1
    first_bundle = bundles[0]
    assert isinstance(first_bundle, dict)
    assert first_bundle["episode_id"] == "hotpotqa-raw-episode-5a8b57f25542995d1e6f1371"


def test_compile_hotpotqa_raw_input_raises_for_missing_context_title(tmp_path: Path) -> None:
    """Verify raw HotpotQA import fails clearly on missing supporting context."""

    source_path = tmp_path / "hotpotqa_raw.json"
    source_path.write_text(
        json.dumps(
            [
                {
                    "_id": "broken-hotpot",
                    "question": "Which country contains Oxford?",
                    "answer": "England",
                    "supporting_facts": [["Oxford", 0]],
                    "context": [["The Hobbit", ["J. R. R. Tolkien wrote The Hobbit."]]],
                }
            ]
        ) + "\n",
        encoding="utf-8",
    )

    try:
        compile_public_dataset_local_slice("hotpotqa", source_path)
    except ValueError as exc:
        assert "missing context title Oxford" in str(exc)
    else:
        raise AssertionError("expected a ValueError for missing HotpotQA context")


def test_compile_locomo_raw_input_to_local_slice_round_trips_through_loader(
    tmp_path: Path,
) -> None:
    """Verify raw LoCoMo-style episodes compile into a loadable normalized slice."""

    payload = compile_public_dataset_local_slice(
        "locomo",
        _locomo_raw_source_path(),
        example_ids=("passport", "departure"),
    )
    output_path = write_public_dataset_local_slice_json(tmp_path / "locomo_slice.json", payload)
    fixture = build_public_dataset_fixture("locomo", source_path=output_path)
    bundles = payload["bundles"]
    assert isinstance(bundles, list)

    assert payload["dataset_version"] == "raw-slice-v1"
    assert len(bundles) == 2
    assert fixture.descriptor.dataset_version == "raw-slice-v1"
    assert fixture.bundles[0].episode_id == "locomo-raw-episode-passport"
    assert fixture.sequence_specs[0].family == "conversation_memory"


def test_compile_locomo_raw_input_respects_max_items() -> None:
    """Verify raw LoCoMo import can compile a bounded episode set."""

    payload = compile_public_dataset_local_slice(
        "locomo",
        _locomo_raw_source_path(),
        max_items=1,
    )

    bundles = payload["bundles"]
    assert isinstance(bundles, list)
    assert len(bundles) == 1
    first_bundle = bundles[0]
    assert isinstance(first_bundle, dict)
    assert first_bundle["episode_id"] == "locomo-raw-episode-passport"


def test_compile_locomo_raw_input_raises_for_missing_reflection(tmp_path: Path) -> None:
    """Verify raw LoCoMo import fails clearly when reflection metadata is missing."""

    source_path = tmp_path / "locomo_raw.json"
    source_path.write_text(
        json.dumps(
            [
                {
                    "episode_id": "broken",
                    "task_id": "locomo-broken-task",
                    "day_offset": 1,
                    "goal": "Remember where the key is.",
                    "result": "The key is in the bag.",
                    "summary": "The key is in the bag.",
                    "recall_question": "Where is the key?",
                    "answer_prompt": "Where is the key?",
                    "answer_kind": "task_result",
                    "required_fragments": ["bag"],
                    "turns": [
                        {"kind": "user_message", "text": "I put the key in the bag."},
                        {"kind": "assistant_message", "text": "Stored memory: key in the bag."}
                    ]
                }
            ]
        ) + "\n",
        encoding="utf-8",
    )

    try:
        compile_public_dataset_local_slice("locomo", source_path)
    except ValueError as exc:
        assert "no supported LoCoMo episodes" in str(exc)
    else:
        raise AssertionError("expected a ValueError for missing LoCoMo reflection")


def _raw_source_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "public_datasets" / "raw" / "scifact"


def _hotpotqa_raw_source_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "data"
        / "public_datasets"
        / "raw"
        / "hotpotqa"
        / "dev_sample.json"
    )


def _locomo_raw_source_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "data"
        / "public_datasets"
        / "raw"
        / "locomo"
        / "conversation_sample.json"
    )