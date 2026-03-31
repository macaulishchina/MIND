from __future__ import annotations

from mind.memory import Memory


def test_build_canonical_text_uses_structured_tag_style() -> None:
    canonical = Memory._build_canonical_text(
        subject_ref="friend:green",
        field_key="occupation",
        field_value_json={"value": "football player"},
    )

    assert canonical == "[friend:green] occupation=football player"


def test_normalize_name_casefolds_and_collapses_whitespace() -> None:
    assert Memory._normalize_name("  Green  ") == "green"
    assert Memory._normalize_name("GrEeN\tSmith") == "green smith"
