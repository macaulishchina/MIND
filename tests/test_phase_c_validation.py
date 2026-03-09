from __future__ import annotations

from mind.fixtures.golden_episode_set import build_core_object_showcase
from mind.kernel.integrity import build_integrity_report
from mind.kernel.schema import validate_object


def test_workspace_view_rejects_slot_count_above_limit() -> None:
    workspace = build_core_object_showcase()[6]
    workspace["metadata"] = dict(workspace["metadata"])
    workspace["metadata"]["slot_limit"] = 1
    workspace["metadata"]["slots"] = list(workspace["metadata"]["slots"]) + [
        {
            "slot_id": "slot-2",
            "summary": "second slot",
            "evidence_refs": ["showcase-raw"],
            "source_refs": ["showcase-summary"],
            "reason_selected": "extra",
            "priority": 0.5,
            "expand_pointer": {"object_id": "showcase-summary"},
        }
    ]

    errors = validate_object(workspace)

    assert "WorkspaceView slot_count must be <= slot_limit" in errors


def test_entity_alias_and_link_confidence_are_typed() -> None:
    showcase = build_core_object_showcase()
    entity = showcase[4]
    link = showcase[5]

    entity["metadata"] = dict(entity["metadata"])
    entity["metadata"]["alias"] = ["ok", ""]
    link["metadata"] = dict(link["metadata"])
    link["metadata"]["confidence"] = 1.5

    entity_errors = validate_object(entity)
    link_errors = validate_object(link)

    assert "EntityNode metadata.alias must be a list of non-empty strings" in entity_errors
    assert "LinkEdge metadata.confidence must be a float in [0, 1]" in link_errors


def test_integrity_report_flags_missing_link_endpoints() -> None:
    showcase = build_core_object_showcase()
    broken_link = showcase[5]
    broken_link["content"] = {
        "src_id": "missing-src",
        "dst_id": showcase[2]["id"],
        "relation_type": "supports",
    }

    report = build_integrity_report(showcase)

    assert ("showcase-link", "missing-src") in report.dangling_refs
