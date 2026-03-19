"""Shared benchmark helper functions for the frontend experience service."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def report_to_payload(report: Any) -> dict[str, Any]:
    """Project a lifecycle benchmark report into the frontend payload shape."""

    return {
        "dataset_name": report.dataset_name,
        "source_path": report.source_path,
        "fixture_name": report.fixture_name,
        "run_id": report.run_id,
        "telemetry_path": report.telemetry_path,
        "store_path": report.store_path,
        "bundle_count": report.bundle_count,
        "answer_case_count": report.answer_case_count,
        "frontend_debug_query": dict(report.frontend_debug_query),
        "notes": list(report.notes),
        "stage_reports": [
            {
                "stage_name": stage.stage_name,
                "ask": {
                    "answer_case_count": stage.ask.answer_case_count,
                    "average_answer_quality": stage.ask.average_answer_quality,
                    "task_success_rate": stage.ask.task_success_rate,
                    "candidate_hit_rate": stage.ask.candidate_hit_rate,
                    "selected_hit_rate": stage.ask.selected_hit_rate,
                    "reuse_rate": stage.ask.reuse_rate,
                    "pollution_rate": stage.ask.pollution_rate,
                },
                "memory": {
                    "active_object_count": stage.memory.active_object_count,
                    "total_object_versions": stage.memory.total_object_versions,
                    "active_object_counts": dict(stage.memory.active_object_counts),
                },
                "cost": {
                    "total_cost": stage.cost.total_cost,
                    "generation_cost": stage.cost.generation_cost,
                    "maintenance_cost": stage.cost.maintenance_cost,
                    "retrieval_cost": stage.cost.retrieval_cost,
                    "read_cost": stage.cost.read_cost,
                    "write_cost": stage.cost.write_cost,
                    "storage_cost": stage.cost.storage_cost,
                    "offline_job_count": stage.cost.offline_job_count,
                },
                "operation_notes": list(stage.operation_notes),
            }
            for stage in report.stage_reports
        ],
    }


_DATASET_LABELS: dict[str, str] = {
    "locomo": "LoCoMo",
    "hotpotqa": "HotpotQA",
    "scifact": "SciFact",
}
_DATASET_ORDER = ("locomo", "hotpotqa", "scifact")
_DATASET_SELECTOR_META: dict[str, dict[str, str]] = {
    "locomo": {
        "raw_source_kind": "json_file",
        "selector_kind": "example_ids",
        "selector_label": "样例编号",
        "selector_placeholder": "可选，多个 example id 用逗号分隔。",
    },
    "hotpotqa": {
        "raw_source_kind": "json_file",
        "selector_kind": "example_ids",
        "selector_label": "样例编号",
        "selector_placeholder": "可选，多个 example id 用逗号分隔。",
    },
    "scifact": {
        "raw_source_kind": "directory",
        "selector_kind": "claim_ids",
        "selector_label": "Claim ID",
        "selector_placeholder": "可选，多个 claim id 用逗号分隔。",
    },
}


def build_benchmark_workspace_payload(
    artifact_root: Path,
    *,
    project_root_resolver: Callable[[], Path] | None = None,
) -> dict[str, Any]:
    """Build the dropdown/search metadata for the lifecycle benchmark workspace."""

    from mind.fixtures import list_public_dataset_descriptors

    resolver = project_root_resolver or _resolve_project_root
    dataset_entries = _build_dataset_entries(
        artifact_root,
        list_public_dataset_descriptors(),
        repo_root=resolver(),
    )
    raw_sources = _build_raw_source_entries(dataset_entries)
    slice_options = _build_slice_entries(artifact_root, dataset_entries)
    report_options = _build_report_entries(artifact_root)
    default_dataset_name = _default_dataset_name(dataset_entries)
    default_slice_path = _default_slice_path(default_dataset_name, dataset_entries, slice_options)
    default_raw_source_path = _default_raw_source_path(
        default_dataset_name,
        dataset_entries,
        raw_sources,
    )
    default_report_run_id = _default_report_run_id(default_dataset_name, report_options)
    default_output_path = (
        str(dataset_entries[default_dataset_name]["default_output_path"])
        if default_dataset_name is not None
        else None
    )
    return {
        "datasets": [
            {
                "dataset_name": entry["dataset_name"],
                "label": entry["label"],
                "summary": entry["summary"],
                "supported_outputs": list(entry["supported_outputs"]),
                "raw_source_kind": entry["raw_source_kind"],
                "selector_kind": entry["selector_kind"],
                "selector_label": entry["selector_label"],
                "selector_placeholder": entry["selector_placeholder"],
                "default_slice_path": _optional_path_string(entry["default_slice_path"]),
                "default_raw_source_path": _optional_path_string(entry["default_raw_source_path"]),
                "default_output_path": str(entry["default_output_path"]),
            }
            for entry in dataset_entries.values()
        ],
        "raw_sources": raw_sources,
        "slice_options": slice_options,
        "report_options": report_options,
        "default_dataset_name": default_dataset_name,
        "default_slice_path": default_slice_path,
        "default_raw_source_path": default_raw_source_path,
        "default_report_run_id": default_report_run_id,
        "default_output_path": default_output_path,
    }


def resolve_dataset_selector_values(
    dataset_name: str,
    selector_values: list[str],
) -> tuple[str | None, tuple[int, ...], tuple[str, ...]]:
    """Normalize typed selector input for slice generation."""

    selector_kind = _DATASET_SELECTOR_META.get(dataset_name, {}).get("selector_kind")
    cleaned_values = tuple(value.strip() for value in selector_values if value.strip())
    if selector_kind == "claim_ids":
        try:
            claim_ids = tuple(int(value) for value in cleaned_values)
        except ValueError as exc:
            raise ValueError("claim id 必须是整数，多个值请用逗号分隔。") from exc
        return selector_kind, claim_ids, ()
    if selector_kind == "example_ids":
        return selector_kind, (), cleaned_values
    return None, (), ()


def coerce_list_payload(payload: dict[str, object], key: str) -> list[object]:
    """Return a payload field as a list or raise a clear validation error."""

    value = payload.get(key)
    if isinstance(value, list):
        return value
    raise ValueError(f"compiled payload field '{key}' must be a list")


def _build_dataset_entries(
    artifact_root: Path,
    descriptors: Any,
    *,
    repo_root: Path,
) -> dict[str, dict[str, Any]]:
    sample_root = _bundled_public_dataset_sample_root()
    generated_root = artifact_root.parent / "public_datasets"
    descriptor_map = {descriptor.dataset_name: descriptor for descriptor in descriptors}
    ordered_names = [
        name for name in _DATASET_ORDER if name in descriptor_map
    ] + sorted(name for name in descriptor_map if name not in _DATASET_ORDER)
    entries: dict[str, dict[str, Any]] = {}
    for dataset_name in ordered_names:
        descriptor = descriptor_map[dataset_name]
        meta = _DATASET_SELECTOR_META.get(
            dataset_name,
            {
                "raw_source_kind": "json_file",
                "selector_kind": None,
                "selector_label": None,
                "selector_placeholder": None,
            },
        )
        default_slice_path = _first_existing_path(
            (
                repo_root
                / "tests"
                / "data"
                / "public_datasets"
                / f"{dataset_name}_local_slice.json",
                sample_root / "slices" / f"{dataset_name}_local_slice.json",
            )
        )
        raw_source_path = _default_raw_source_path_for_dataset(repo_root, sample_root, dataset_name)
        entries[dataset_name] = {
            "dataset_name": dataset_name,
            "label": _DATASET_LABELS.get(dataset_name, dataset_name),
            "summary": descriptor.summary,
            "supported_outputs": tuple(descriptor.supported_outputs),
            "default_slice_path": default_slice_path,
            "default_raw_source_path": raw_source_path,
            "default_output_path": generated_root / f"{dataset_name}_raw_compiled_slice.json",
            "raw_source_kind": meta["raw_source_kind"],
            "selector_kind": meta["selector_kind"],
            "selector_label": meta["selector_label"],
            "selector_placeholder": meta["selector_placeholder"],
        }
    return entries


def _build_raw_source_entries(
    dataset_entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for dataset_name in _ordered_dataset_names(dataset_entries):
        raw_source_path = dataset_entries[dataset_name]["default_raw_source_path"]
        if raw_source_path is None:
            continue
        entries.append(
            {
                "dataset_name": dataset_name,
                "source_path": str(raw_source_path),
                "label": f"仓库样例 raw · {raw_source_path.name}",
                "origin": "sample",
                "path_kind": dataset_entries[dataset_name]["raw_source_kind"],
            }
        )
    return entries


def _build_slice_entries(
    artifact_root: Path,
    dataset_entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for dataset_name in _ordered_dataset_names(dataset_entries):
        default_slice_path = dataset_entries[dataset_name]["default_slice_path"]
        if default_slice_path is None:
            continue
        summary = _read_local_slice_summary(default_slice_path)
        if summary is None:
            continue
        options.append(
            {
                "dataset_name": dataset_name,
                "source_path": str(default_slice_path),
                "label": f"仓库样例 slice · {default_slice_path.name}",
                "origin": "sample",
                "bundle_count": summary["bundle_count"],
                "updated_at": summary["updated_at"],
            }
        )
        seen.add(default_slice_path.resolve())

    generated_root = artifact_root.parent / "public_datasets"
    if generated_root.exists():
        for path in sorted(generated_root.rglob("*.json"), key=_path_mtime, reverse=True):
            resolved = path.resolve()
            if resolved in seen:
                continue
            summary = _read_local_slice_summary(path)
            if summary is None:
                continue
            options.append(
                {
                    "dataset_name": summary["dataset_name"],
                    "source_path": str(path),
                    "label": f"已生成 slice · {path.name}",
                    "origin": "generated",
                    "bundle_count": summary["bundle_count"],
                    "updated_at": summary["updated_at"],
                }
            )
            seen.add(resolved)

    return options


def _build_report_entries(artifact_root: Path) -> list[dict[str, Any]]:
    from mind.eval import read_memory_lifecycle_benchmark_report_json

    options: list[dict[str, Any]] = []
    latest_assigned = False
    report_paths = sorted(
        artifact_root.glob("*/report.json"),
        key=_path_mtime,
        reverse=True,
    )
    for report_path in report_paths:
        try:
            report = read_memory_lifecycle_benchmark_report_json(report_path)
        except (FileNotFoundError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        updated_at = _path_timestamp(report_path)
        options.append(
            {
                "run_id": report.run_id,
                "dataset_name": report.dataset_name,
                "source_path": report.source_path,
                "label": (
                    f"{report.dataset_name} · {report.run_id} · "
                    f"{_short_timestamp(updated_at)}"
                ),
                "report_path": str(report_path),
                "updated_at": updated_at,
                "is_latest": not latest_assigned,
            }
        )
        latest_assigned = True
    return options


def _default_dataset_name(dataset_entries: dict[str, dict[str, Any]]) -> str | None:
    ordered = _ordered_dataset_names(dataset_entries)
    return ordered[0] if ordered else None


def _default_slice_path(
    dataset_name: str | None,
    dataset_entries: dict[str, dict[str, Any]],
    slice_options: list[dict[str, Any]],
) -> str | None:
    if dataset_name is None:
        return None
    matching_option = next(
        (
            option["source_path"]
            for option in slice_options
            if option["dataset_name"] == dataset_name
        ),
        None,
    )
    if matching_option is not None:
        return str(matching_option)
    return _optional_path_string(dataset_entries[dataset_name]["default_slice_path"])


def _default_raw_source_path(
    dataset_name: str | None,
    dataset_entries: dict[str, dict[str, Any]],
    raw_sources: list[dict[str, Any]],
) -> str | None:
    if dataset_name is None:
        return None
    matching_option = next(
        (
            option["source_path"]
            for option in raw_sources
            if option["dataset_name"] == dataset_name
        ),
        None,
    )
    if matching_option is not None:
        return str(matching_option)
    return _optional_path_string(dataset_entries[dataset_name]["default_raw_source_path"])


def _default_report_run_id(
    dataset_name: str | None,
    report_options: list[dict[str, Any]],
) -> str | None:
    if dataset_name is not None:
        matching = next(
            (
                option["run_id"]
                for option in report_options
                if option["dataset_name"] == dataset_name
            ),
            None,
        )
        if matching is not None:
            return str(matching)
    if not report_options:
        return None
    return str(report_options[0]["run_id"])


def _default_raw_source_path_for_dataset(
    repo_root: Path,
    sample_root: Path,
    dataset_name: str,
) -> Path | None:
    if dataset_name == "scifact":
        return _first_existing_path(
            (
                repo_root / "tests" / "data" / "public_datasets" / "raw" / "scifact",
                sample_root / "raw" / "scifact",
            )
        )
    if dataset_name == "hotpotqa":
        return _first_existing_path(
            (
                repo_root
                / "tests"
                / "data"
                / "public_datasets"
                / "raw"
                / "hotpotqa"
                / "dev_sample.json",
                sample_root / "raw" / "hotpotqa" / "dev_sample.json",
            )
        )
    return _first_existing_path(
        (
            repo_root
            / "tests"
            / "data"
            / "public_datasets"
            / "raw"
            / "locomo"
            / "conversation_sample.json",
            sample_root / "raw" / "locomo" / "conversation_sample.json",
        )
    )


def _resolve_project_root() -> Path:
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    file_path = Path(__file__).resolve()
    candidates.extend([file_path.parent, *file_path.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "tests" / "data" / "public_datasets").exists():
            return candidate
    return cwd


def _bundled_public_dataset_sample_root() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "public_datasets" / "dev_samples"


def _first_existing_path(candidates: tuple[Path, ...]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_local_slice_summary(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    bundles = payload.get("bundles")
    if not isinstance(bundles, list):
        return None
    dataset_name = _detect_dataset_name_from_slice_payload(path, bundles)
    if dataset_name is None:
        return None
    return {
        "dataset_name": dataset_name,
        "bundle_count": len(bundles),
        "updated_at": _path_timestamp(path),
    }


def _detect_dataset_name_from_slice_payload(
    path: Path,
    bundles: list[Any],
) -> str | None:
    known_names = set(_DATASET_LABELS)
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        tags = bundle.get("tags")
        if not isinstance(tags, list):
            continue
        dataset_tags = [tag for tag in tags if isinstance(tag, str) and tag in known_names]
        if dataset_tags:
            return dataset_tags[0]
    stem = path.stem.lower()
    for dataset_name in _DATASET_ORDER:
        if dataset_name in stem:
            return dataset_name
    return None


def _optional_path_string(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _ordered_dataset_names(dataset_entries: dict[str, dict[str, Any]]) -> list[str]:
    ordered = [name for name in _DATASET_ORDER if name in dataset_entries]
    ordered.extend(sorted(name for name in dataset_entries if name not in _DATASET_ORDER))
    return ordered


def _path_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _short_timestamp(value: str) -> str:
    return value.replace("T", " ").replace("+00:00", " UTC")


def _path_mtime(path: Path) -> float:
    return path.stat().st_mtime
