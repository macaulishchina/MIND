"""Direct provenance models and helpers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceModel(BaseModel):
    """Strict base model shared by provenance ledger records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProducerKind(StrEnum):
    USER = "user"
    MODEL = "model"
    TOOL = "tool"
    SYSTEM = "system"
    OPERATOR = "operator"
    DATASET = "dataset"


class SourceChannel(StrEnum):
    CHAT = "chat"
    API = "api"
    BATCH_IMPORT = "batch_import"
    TOOL_RUNTIME = "tool_runtime"
    SYSTEM_INTERNAL = "system_internal"


class RetentionClass(StrEnum):
    DEFAULT = "default"
    SENSITIVE = "sensitive"
    EPHEMERAL = "ephemeral"
    REGULATED = "regulated"


HIGH_SENSITIVITY_PROVENANCE_FIELDS = frozenset(
    {
        "ip_addr",
        "device_id",
        "machine_fingerprint",
        "session_id",
        "request_id",
        "conversation_id",
    }
)


class DirectProvenanceInput(ProvenanceModel):
    producer_kind: ProducerKind
    producer_id: str = Field(min_length=1)
    captured_at: datetime
    source_channel: SourceChannel
    tenant_id: str = Field(min_length=1)
    retention_class: RetentionClass = RetentionClass.DEFAULT
    user_id: str | None = None
    model_id: str | None = None
    model_provider: str | None = None
    model_version: str | None = None
    ip_addr: str | None = None
    device_id: str | None = None
    machine_fingerprint: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    conversation_id: str | None = None
    episode_id: str | None = None


class DirectProvenanceRecord(DirectProvenanceInput):
    provenance_id: str = Field(min_length=1)
    bound_object_id: str = Field(min_length=1)
    bound_object_type: Literal["RawRecord", "ImportedRawRecord"]
    ingested_at: datetime


class ProvenanceSummary(ProvenanceModel):
    provenance_id: str = Field(min_length=1)
    producer_kind: ProducerKind
    producer_id: str = Field(min_length=1)
    captured_at: datetime
    ingested_at: datetime
    source_channel: SourceChannel
    tenant_id: str = Field(min_length=1)
    retention_class: RetentionClass
    user_id: str | None = None
    model_id: str | None = None
    model_provider: str | None = None
    model_version: str | None = None
    episode_id: str | None = None


def build_direct_provenance_record(
    *,
    provenance_id: str,
    bound_object_id: str,
    bound_object_type: Literal["RawRecord", "ImportedRawRecord"],
    direct_provenance: DirectProvenanceInput | None,
    actor: str,
    ingested_at: datetime,
    episode_id: str | None,
) -> DirectProvenanceRecord:
    """Materialize a ledger record, using a deterministic fallback when needed."""

    if direct_provenance is None:
        payload = DirectProvenanceInput(
            producer_kind=ProducerKind.SYSTEM,
            producer_id=actor,
            captured_at=ingested_at,
            source_channel=SourceChannel.SYSTEM_INTERNAL,
            tenant_id="default",
            retention_class=RetentionClass.DEFAULT,
            episode_id=episode_id,
        ).model_dump()
    else:
        payload = direct_provenance.model_dump()
        bound_episode_id = payload.get("episode_id")
        if bound_episode_id is None and episode_id is not None:
            payload["episode_id"] = episode_id
        elif episode_id is not None and bound_episode_id != episode_id:
            raise ValueError(
                "direct provenance episode_id must match the bound RawRecord episode_id"
            )

    return DirectProvenanceRecord(
        provenance_id=provenance_id,
        bound_object_id=bound_object_id,
        bound_object_type=bound_object_type,
        ingested_at=ingested_at,
        **payload,
    )


def build_provenance_summary(
    record: DirectProvenanceRecord | dict[str, object],
) -> ProvenanceSummary:
    """Project a direct provenance record into the runtime-safe summary surface."""

    validated = DirectProvenanceRecord.model_validate(record)
    return ProvenanceSummary(
        provenance_id=validated.provenance_id,
        producer_kind=validated.producer_kind,
        producer_id=validated.producer_id,
        captured_at=validated.captured_at,
        ingested_at=validated.ingested_at,
        source_channel=validated.source_channel,
        tenant_id=validated.tenant_id,
        retention_class=validated.retention_class,
        user_id=validated.user_id,
        model_id=validated.model_id,
        model_provider=validated.model_provider,
        model_version=validated.model_version,
        episode_id=validated.episode_id,
    )
