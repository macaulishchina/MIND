"""Integrity checks for the Phase B memory kernel."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .schema import validate_object


@dataclass(frozen=True)
class IntegrityReport:
    source_trace_coverage: float
    metadata_coverage: float
    dangling_refs: list[tuple[str, str]]
    cycles: list[list[str]]
    version_chain_issues: list[str]


def build_integrity_report(objects: Iterable[dict]) -> IntegrityReport:
    all_objects = list(objects)
    object_ids = {obj["id"] for obj in all_objects}

    derived = [obj for obj in all_objects if obj["type"] != "RawRecord"]
    valid_trace_count = 0
    dangling_refs: list[tuple[str, str]] = []

    for obj in derived:
        refs = obj["source_refs"]
        if refs and all(ref in object_ids for ref in refs):
            valid_trace_count += 1
        for ref in refs:
            if ref not in object_ids:
                dangling_refs.append((obj["id"], ref))

    source_trace_coverage = 1.0 if not derived else valid_trace_count / len(derived)

    metadata_valid = 0
    for obj in all_objects:
        if not validate_object(obj):
            metadata_valid += 1
    metadata_coverage = 1.0 if not all_objects else metadata_valid / len(all_objects)

    return IntegrityReport(
        source_trace_coverage=source_trace_coverage,
        metadata_coverage=metadata_coverage,
        dangling_refs=dangling_refs,
        cycles=_find_cycles(all_objects),
        version_chain_issues=_find_version_chain_issues(all_objects),
    )


def _find_cycles(objects: list[dict]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for obj in objects:
        graph.setdefault(obj["id"], set()).update(obj["source_refs"])

    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        visiting.add(node)
        stack.append(node)

        for neighbor in sorted(graph.get(node, ())):
            if neighbor not in graph:
                continue
            if neighbor in visiting:
                start = stack.index(neighbor)
                cycles.append(stack[start:] + [neighbor])
                continue
            if neighbor not in visited:
                dfs(neighbor)

        visiting.remove(node)
        stack.pop()

    for node in sorted(graph):
        if node not in visited:
            dfs(node)
    return cycles


def _find_version_chain_issues(objects: list[dict]) -> list[str]:
    grouped: dict[str, list[int]] = {}
    for obj in objects:
        grouped.setdefault(obj["id"], []).append(int(obj["version"]))

    issues: list[str] = []
    for object_id, versions in grouped.items():
        ordered = sorted(versions)
        expected = list(range(1, len(ordered) + 1))
        if ordered != expected:
            issues.append(f"{object_id}: expected versions {expected}, got {ordered}")
    return issues

