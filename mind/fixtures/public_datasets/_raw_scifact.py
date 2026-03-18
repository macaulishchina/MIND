"""SciFact raw-import compilation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compile_scifact_local_slice(
    source_dir: Path,
    *,
    claim_ids: tuple[int, ...],
    max_items: int | None,
) -> dict[str, object]:
    """Compile a SciFact raw directory into a normalized local-slice payload."""

    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be >= 1 when provided")

    claims_path = source_dir / "claims.jsonl"
    corpus_path = source_dir / "corpus.jsonl"
    claims = _read_jsonl_objects(claims_path)
    corpus = _read_jsonl_objects(corpus_path)
    corpus_by_id = {str(item["doc_id"]): item for item in corpus}

    selected_claims = _select_scifact_claims(
        claims,
        corpus_by_id=corpus_by_id,
        claim_ids=claim_ids,
        max_items=max_items,
    )
    bundles = [
        _build_scifact_bundle_payload(claim, index=index, corpus_by_id=corpus_by_id)
        for index, claim in enumerate(selected_claims, start=1)
    ]
    sequence_spec = _build_scifact_sequence_payload(bundles)
    return {
        "dataset_version": "raw-slice-v1",
        "bundles": bundles,
        "sequence_specs": [sequence_spec],
    }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _select_scifact_claims(
    claims: list[dict[str, Any]],
    *,
    corpus_by_id: dict[str, dict[str, Any]],
    claim_ids: tuple[int, ...],
    max_items: int | None,
) -> list[dict[str, Any]]:
    eligible_claims = [
        claim
        for claim in claims
        if _normalize_scifact_label(claim.get("label")) is not None
        and _claim_evidence_doc_ids(claim)
    ]
    claim_by_id = {
        int(claim["id"]): claim
        for claim in eligible_claims
    }

    if claim_ids:
        selected_claims: list[dict[str, Any]] = []
        for claim_id in claim_ids:
            claim = claim_by_id.get(claim_id)
            if claim is None:
                raise ValueError(f"unknown or unsupported SciFact claim id: {claim_id}")
            selected_claims.append(claim)
    else:
        limit = max_items if max_items is not None else 2
        selected_claims = eligible_claims[:limit]

    for claim in selected_claims:
        for doc_id in _claim_evidence_doc_ids(claim):
            if doc_id not in corpus_by_id:
                raise ValueError(
                    f"SciFact claim {claim['id']} references missing corpus doc_id {doc_id}"
                )

    if not selected_claims:
        raise ValueError("no supported SciFact claims were selected from the raw inputs")
    return selected_claims


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------


def _build_scifact_bundle_payload(
    claim: dict[str, Any],
    *,
    index: int,
    corpus_by_id: dict[str, dict[str, Any]],
) -> dict[str, object]:
    claim_id = int(claim["id"])
    label = _normalize_scifact_label(claim.get("label"))
    if label is None:
        raise ValueError(f"SciFact claim {claim_id} has unsupported label")
    claim_text = _read_required_string(claim, "claim")
    evidence_text = _build_scifact_evidence_text(claim, corpus_by_id)
    episode_id = f"scifact-raw-episode-{claim_id}"
    task_id = f"scifact-raw-task-{claim_id}"
    summary_text = (
        f"The claim is {label.lower()} because the cited evidence says {evidence_text}."
    )

    return {
        "bundle_id": f"scifact_raw_bundle_{claim_id}",
        "task_id": task_id,
        "episode_id": episode_id,
        "day_offset": 100 + index,
        "goal": f"Assess whether the following claim is supported: {claim_text}",
        "result": f"{label}: {claim_text}",
        "success": True,
        "summary": summary_text,
        "raw_records": [
            {
                "kind": "user_message",
                "text": f"Claim: {claim_text}",
            },
            {
                "kind": "tool_result",
                "text": f"Evidence abstract: {evidence_text}",
            },
        ],
        "retrieval_specs": [
            {
                "case_key": f"claim_{claim_id}_keyword",
                "query": claim_text,
                "query_modes": ["keyword"],
                "filters": {
                    "object_types": ["RawRecord", "TaskEpisode", "SummaryNote"],
                },
                "gold_candidate_refs": ["record:1", "record:2", "episode", "summary"],
                "gold_fact_refs": ["record:2", "episode", "summary"],
                "slot_limit": 4,
            }
        ],
        "answer_specs": [
            {
                "case_key": f"claim_{claim_id}_keyword",
                "prompt": f"What is the verdict for the claim '{claim_text}'?",
                "answer_kind": "task_result",
                "required_fragments": [label, *_claim_fragments(claim_text)],
                "gold_fact_refs": ["record:2", "episode", "summary"],
                "gold_memory_refs": ["episode", "summary"],
                "max_answer_tokens": 20,
            }
        ],
        "tags": ["public_dataset", "scifact", "raw_import"],
    }


# ---------------------------------------------------------------------------
# Sequence building
# ---------------------------------------------------------------------------


def _build_scifact_sequence_payload(
    bundles: list[dict[str, object]],
) -> dict[str, object]:
    candidate_ids: list[str] = []
    steps: list[dict[str, object]] = []
    for index, bundle in enumerate(bundles, start=1):
        episode_id = str(bundle["episode_id"])
        task_id = str(bundle["task_id"])
        summary_id = f"{episode_id}-summary"
        evidence_id = f"{episode_id}-raw-02"
        candidate_ids.extend((summary_id, episode_id, evidence_id))
        steps.append(
            {
                "step_key": f"step_{index:02d}",
                "task_id": task_id,
                "needed_object_ids": [summary_id],
            }
        )

    episode_ids = [str(bundle["episode_id"]) for bundle in bundles]
    evidence_ids = [f"{episode_id}-raw-02" for episode_id in episode_ids]
    if len(episode_ids) == 1:
        steps.extend(
            (
                {
                    "step_key": f"step_{len(steps) + 1:02d}",
                    "task_id": str(bundles[0]["task_id"]),
                    "needed_object_ids": episode_ids,
                },
                {
                    "step_key": f"step_{len(steps) + 2:02d}",
                    "task_id": str(bundles[0]["task_id"]),
                    "needed_object_ids": evidence_ids,
                },
            )
        )
    else:
        combined_task_id = "+".join(str(bundle["task_id"]) for bundle in bundles)
        steps.extend(
            (
                {
                    "step_key": f"step_{len(steps) + 1:02d}",
                    "task_id": combined_task_id,
                    "needed_object_ids": episode_ids,
                },
                {
                    "step_key": f"step_{len(steps) + 2:02d}",
                    "task_id": combined_task_id,
                    "needed_object_ids": evidence_ids,
                },
            )
        )

    return {
        "sequence_key": "claim_review_raw_import",
        "family": "evidence_comparison",
        "candidate_ids": candidate_ids,
        "steps": steps,
        "tags": ["public_dataset", "scifact", "raw_import"],
        "maintenance_target_refs": [],
    }


# ---------------------------------------------------------------------------
# Evidence text
# ---------------------------------------------------------------------------


def _build_scifact_evidence_text(
    claim: dict[str, Any],
    corpus_by_id: dict[str, dict[str, Any]],
) -> str:
    evidence = claim.get("evidence")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError(f"SciFact claim {claim['id']} has no usable evidence map")

    snippets: list[str] = []
    for doc_id, entries in evidence.items():
        corpus_entry = corpus_by_id.get(str(doc_id))
        if corpus_entry is None:
            raise ValueError(
                f"SciFact claim {claim['id']} references missing corpus doc_id {doc_id}"
            )
        if not isinstance(entries, list) or not entries:
            continue
        abstract = corpus_entry.get("abstract")
        if not isinstance(abstract, list) or not all(
            isinstance(item, str) for item in abstract
        ):
            raise ValueError(
                f"SciFact corpus doc_id {doc_id} has invalid abstract format"
            )
        sentence_indexes = _extract_sentence_indexes(entries)
        selected_sentences = [
            abstract[index]
            for index in sentence_indexes
            if 0 <= index < len(abstract)
        ]
        if not selected_sentences and abstract:
            selected_sentences = [abstract[0]]
        title = str(corpus_entry.get("title", f"doc {doc_id}"))
        if selected_sentences:
            snippets.append(f"{title}: {' '.join(selected_sentences)}")

    if not snippets:
        raise ValueError(
            f"SciFact claim {claim['id']} did not yield any evidence snippets"
        )
    return " ".join(snippets)


# ---------------------------------------------------------------------------
# Shared low-level helpers
# ---------------------------------------------------------------------------


def _extract_sentence_indexes(entries: list[Any]) -> list[int]:
    indexes: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("sentences")
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, int):
                indexes.append(item)
    return indexes


def _claim_evidence_doc_ids(claim: dict[str, Any]) -> tuple[str, ...]:
    evidence = claim.get("evidence")
    if not isinstance(evidence, dict):
        return ()
    return tuple(
        str(doc_id)
        for doc_id, entries in evidence.items()
        if isinstance(entries, list)
    )


def _normalize_scifact_label(raw_label: object) -> str | None:
    if not isinstance(raw_label, str):
        return None
    label = raw_label.strip().upper()
    if label == "SUPPORT":
        return "Supported"
    if label == "CONTRADICT":
        return "Refuted"
    return None


def _claim_fragments(claim_text: str) -> list[str]:
    stopwords = {
        "the",
        "and",
        "that",
        "with",
        "from",
        "this",
        "every",
        "some",
        "into",
        "does",
        "about",
        "their",
    }
    fragments: list[str] = []
    for token in claim_text.replace("-", " ").replace(".", " ").split():
        normalized = token.strip(" ,:;!?()[]{}\"'")
        if len(normalized) < 4 or normalized.lower() in stopwords:
            continue
        if normalized in fragments:
            continue
        fragments.append(normalized)
        if len(fragments) == 2:
            break
    if not fragments:
        fragments.append(claim_text.split()[0])
    return fragments


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(
            f"raw public dataset source is missing required file: {path}"
        )
    items: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(
                f"JSONL line {line_number} in {path} must be an object"
            )
        items.append(payload)
    return items


def _read_required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"field '{key}' must be a non-empty string")
    return value.strip()
