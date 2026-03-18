#!/usr/bin/env python3
"""Compile raw public-dataset inputs into normalized local slices."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mind.fixtures.public_datasets import (  # noqa: E402
    compile_public_dataset_local_slice,
    write_public_dataset_local_slice_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile raw public-dataset inputs into a normalized local slice JSON.",
    )
    parser.add_argument(
        "dataset",
        help="Dataset name, currently scifact, hotpotqa, or locomo.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory containing the raw dataset files.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the normalized local slice JSON.",
    )
    parser.add_argument(
        "--claim-id",
        type=int,
        action="append",
        default=[],
        help="Optional SciFact claim id to include. May be passed multiple times.",
    )
    parser.add_argument(
        "--example-id",
        action="append",
        default=[],
        help="Optional HotpotQA or LoCoMo example id to include. May be passed multiple times.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional maximum number of raw items to compile when ids are not given.",
    )
    args = parser.parse_args()

    payload = compile_public_dataset_local_slice(
        args.dataset,
        args.source,
        claim_ids=tuple(args.claim_id),
        example_ids=tuple(args.example_id),
        max_items=args.max_items,
    )
    output_path = write_public_dataset_local_slice_json(args.output, payload)
    bundles = payload.get("bundles", [])
    if not isinstance(bundles, list):
        raise ValueError("compiled payload field 'bundles' must be a list")
    sequence_specs = payload.get("sequence_specs", [])
    if not isinstance(sequence_specs, list):
        raise ValueError("compiled payload field 'sequence_specs' must be a list")
    bundle_count = len(bundles)
    sequence_count = len(sequence_specs)
    print("Public dataset local slice compiled")
    print(f"dataset_name={args.dataset}")
    print(f"source_path={args.source}")
    print(f"output_path={output_path}")
    print(f"bundle_count={bundle_count}")
    print(f"sequence_count={sequence_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())