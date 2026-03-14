"""Evidence and promotion audit helpers."""

from __future__ import annotations

from dataclasses import dataclass

from mind.fixtures.long_horizon_dev import LongHorizonSequence
from mind.kernel.retrieval import build_search_text, tokenize
from mind.kernel.store import MemoryStore

_RULE_STOPWORDS = {
    "a",
    "across",
    "and",
    "cross",
    "episode",
    "from",
    "objects",
    "pattern",
    "promote",
    "repeated",
    "support",
}


@dataclass(frozen=True)
class SchemaEvidenceAudit:
    schema_object_id: str
    evidence_ref_count: int
    supported_evidence_ref_count: int
    precision: float
    supported: bool


@dataclass(frozen=True)
class PromotionAudit:
    schema_object_id: str
    reused_within_window: bool
    remains_active: bool
    precise: bool


def audit_schema_evidence(
    store: MemoryStore,
    schema_object_id: str,
) -> SchemaEvidenceAudit:
    """Audit whether a synthesized schema is supported by its evidence refs."""

    schema_object = store.read_object(schema_object_id)
    metadata = schema_object.get("metadata", {})
    evidence_refs = tuple(
        str(ref) for ref in metadata.get("evidence_refs", schema_object["source_refs"])
    )
    rule_tokens = _rule_tokens(str(schema_object.get("content", {}).get("rule", "")))
    supported_count = 0
    for ref in evidence_refs:
        evidence_object = store.read_object(ref)
        evidence_tokens = tokenize(build_search_text(evidence_object))
        if rule_tokens.intersection(evidence_tokens):
            supported_count += 1

    precision = _safe_ratio(supported_count, len(evidence_refs))
    return SchemaEvidenceAudit(
        schema_object_id=schema_object_id,
        evidence_ref_count=len(evidence_refs),
        supported_evidence_ref_count=supported_count,
        precision=precision,
        supported=(len(evidence_refs) > 0 and precision == 1.0),
    )


def audit_promotion_within_window(
    store: MemoryStore,
    schema_object_id: str,
    sequence: LongHorizonSequence,
) -> PromotionAudit:
    """Audit whether a promoted schema remains active and becomes reusable soon after promotion."""

    schema_object = store.read_object(schema_object_id)
    metadata = schema_object.get("metadata", {})
    promotion_source_refs = tuple(
        str(ref) for ref in metadata.get("promotion_source_refs", schema_object["source_refs"])
    )
    future_needed_refs = {
        object_id for step in sequence.steps[:10] for object_id in step.needed_object_ids
    }
    remains_active = schema_object["status"] not in {"archived", "deprecated", "invalid"}
    reused_within_window = bool(set(promotion_source_refs).intersection(future_needed_refs))
    return PromotionAudit(
        schema_object_id=schema_object_id,
        reused_within_window=reused_within_window,
        remains_active=remains_active,
        precise=(remains_active and reused_within_window),
    )


def _rule_tokens(rule: str) -> set[str]:
    return {token for token in tokenize(rule) if token not in _RULE_STOPWORDS}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / float(denominator), 4)
