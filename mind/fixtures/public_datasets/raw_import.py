"""Compile raw public-dataset inputs into normalized local slices.

This module is a thin dispatcher that delegates to dataset-specific
compilation helpers in ``_raw_scifact``, ``_raw_hotpotqa``, and
``_raw_locomo``.
"""

from __future__ import annotations

import json
from pathlib import Path

from mind.fixtures.public_datasets._raw_hotpotqa import (
    compile_hotpotqa_local_slice,
)
from mind.fixtures.public_datasets._raw_locomo import (
    compile_locomo_local_slice,
)
from mind.fixtures.public_datasets._raw_scifact import (
    compile_scifact_local_slice,
)


def compile_public_dataset_local_slice(
    dataset_name: str,
    source_path: str | Path,
    *,
    claim_ids: tuple[int, ...] = (),
    example_ids: tuple[str, ...] = (),
    max_items: int | None = None,
) -> dict[str, object]:
    """Compile a raw dataset input into a normalized local-slice payload."""

    if dataset_name == "scifact":
        return _compile_scifact_local_slice(
            Path(source_path),
            claim_ids=claim_ids,
            max_items=max_items,
        )
    if dataset_name == "hotpotqa":
        return _compile_hotpotqa_local_slice(
            Path(source_path),
            example_ids=example_ids,
            max_items=max_items,
        )
    if dataset_name == "locomo":
        return _compile_locomo_local_slice(
            Path(source_path),
            example_ids=example_ids,
            max_items=max_items,
        )
    raise ValueError(
        "raw public dataset import is currently implemented only for "
        "scifact, hotpotqa, and locomo"
    )


def write_public_dataset_local_slice_json(
    path: str | Path,
    payload: dict[str, object],
) -> Path:
    """Persist a normalized public-dataset local slice as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return output_path


# ---------------------------------------------------------------------------
# Private per-dataset entry points (read raw files & delegate)
# ---------------------------------------------------------------------------


def _compile_scifact_local_slice(
    source_dir: Path,
    *,
    claim_ids: tuple[int, ...],
    max_items: int | None,
) -> dict[str, object]:
    return compile_scifact_local_slice(
        source_dir,
        claim_ids=claim_ids,
        max_items=max_items,
    )


def _compile_hotpotqa_local_slice(
    source_path: Path,
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> dict[str, object]:
    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be >= 1 when provided")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(
            "HotpotQA raw source must be a JSON list of examples"
        )
    examples = [item for item in payload if isinstance(item, dict)]

    bundles, sequence_spec = compile_hotpotqa_local_slice(
        examples,
        example_ids=example_ids,
        max_items=max_items,
    )
    return {
        "dataset_version": "raw-slice-v1",
        "bundles": bundles,
        "sequence_specs": [sequence_spec],
    }


def _compile_locomo_local_slice(
    source_path: Path,
    *,
    example_ids: tuple[str, ...],
    max_items: int | None,
) -> dict[str, object]:
    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be >= 1 when provided")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(
            "LoCoMo raw source must be a JSON list of episodes"
        )
    examples = [item for item in payload if isinstance(item, dict)]

    bundles, sequence_spec = compile_locomo_local_slice(
        examples,
        example_ids=example_ids,
        max_items=max_items,
    )
    return {
        "dataset_version": "raw-slice-v1",
        "bundles": bundles,
        "sequence_specs": [sequence_spec],
    }