"""System health report (Phase α-S2).

Provides :func:`compute_health_report` which aggregates object-type counts,
status distribution, average priority, pending-job count, and orphan references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mind.kernel.store import MemoryStore


@dataclass
class HealthReport:
    """Snapshot of memory-system health."""

    total_objects: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    average_priority: float = 0.0
    pending_jobs: int = 0
    orphan_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_objects": self.total_objects,
            "type_counts": self.type_counts,
            "status_counts": self.status_counts,
            "average_priority": round(self.average_priority, 4),
            "pending_jobs": self.pending_jobs,
            "orphan_refs": self.orphan_refs,
        }


def compute_health_report(store: MemoryStore) -> HealthReport:
    """Scan the store and produce a :class:`HealthReport`."""
    report = HealthReport()

    # Gather all latest objects.
    all_objects = store.iter_objects()
    known_ids: set[str] = set()
    priority_sum = 0.0

    for obj in all_objects:
        known_ids.add(obj["id"])
        report.type_counts[obj["type"]] = report.type_counts.get(obj["type"], 0) + 1
        report.status_counts[obj["status"]] = report.status_counts.get(obj["status"], 0) + 1
        priority_sum += float(obj.get("priority", 0.5))

    report.total_objects = len(all_objects)
    if report.total_objects > 0:
        report.average_priority = priority_sum / report.total_objects

    # Orphan source_refs detection.
    for obj in all_objects:
        for ref in obj.get("source_refs", []):
            if ref and ref not in known_ids:
                report.orphan_refs.append(ref)

    # Pending job count.
    try:
        pending_jobs = list(store.iter_latest_objects(statuses=["pending"]))
        report.pending_jobs = len(pending_jobs)
    except Exception:
        pass  # store may not support jobs

    return report
