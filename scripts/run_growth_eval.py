#!/usr/bin/env python3
"""Run growth evaluation: compute growth metrics (Phase α-4.5).

Usage::

    uv run python scripts/run_growth_eval.py
    uv run python scripts/run_growth_eval.py --output report.json
"""

from __future__ import annotations

import argparse
import json
import sys

from mind.app.registry import build_app_registry
from mind.cli_config import resolve_cli_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run growth evaluation metrics.")
    parser.add_argument("--output", "-o", default=None, help="Write JSON report to file.")
    args = parser.parse_args()

    config = resolve_cli_config(allow_sqlite=True)
    with build_app_registry(config) as registry:
        store = registry.store

        # Gather object inventory
        all_objects = store.iter_objects()
        total_objects = len(all_objects)

        type_counts: dict[str, int] = {}
        feedback_objects: list[dict] = []
        for obj in all_objects:
            obj_type = obj.get("type", "unknown")
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
            if obj_type == "FeedbackRecord":
                feedback_objects.append(obj)

        # Compute memory efficiency
        total_quality = sum(
            float(obj.get("metadata", {}).get("quality_signal", 0))
            for obj in feedback_objects
        )
        task_ids = {
            obj.get("metadata", {}).get("task_id")
            for obj in all_objects
            if obj.get("metadata", {}).get("task_id")
        }
        task_count = len(task_ids)
        memory_efficiency = (
            round((total_quality * task_count) / max(total_objects, 1), 4)
            if total_objects > 0
            else 0.0
        )

        # Feedback correlation (positive vs negative reuse signal)
        positive_count = sum(
            len(obj.get("metadata", {}).get("helpful_object_ids", []))
            for obj in feedback_objects
        )
        negative_count = sum(
            len(obj.get("metadata", {}).get("unhelpful_object_ids", []))
            for obj in feedback_objects
        )
        feedback_correlation = round(
            (positive_count - negative_count) / max(positive_count + negative_count, 1), 4
        )

        # Pending jobs
        try:
            pending_jobs = len(store.iter_latest_objects(statuses=["pending"]))
        except Exception:
            pending_jobs = 0

        report = {
            "total_objects": total_objects,
            "type_counts": type_counts,
            "feedback_count": len(feedback_objects),
            "task_count": task_count,
            "memory_efficiency": memory_efficiency,
            "feedback_correlation": feedback_correlation,
            "positive_feedback_refs": positive_count,
            "negative_feedback_refs": negative_count,
            "pending_jobs": pending_jobs,
        }

        output = json.dumps(report, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output + "\n")
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(output)


if __name__ == "__main__":
    main()
