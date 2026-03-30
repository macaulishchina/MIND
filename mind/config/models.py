"""Pure data models and enums — no configuration logic."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class MemoryType(str, Enum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    EVENT = "event"
    GENERAL = "general"


class MemoryOperation(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NONE = "NONE"


class OwnerType(str, Enum):
    KNOWN = "known"
    ANONYMOUS = "anonymous"


class FactFamily(str, Enum):
    ATTRIBUTE = "attribute"
    PREFERENCE = "preference"
    RELATION = "relation"
    EVENT = "event"
    PLAN = "plan"
    QUOTE = "quote"
    BELIEF = "belief"
    HABIT = "habit"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class MemoryItem(BaseModel):
    """Core memory representation (two-layer design)."""

    # Core layer
    id: str
    user_id: str
    owner_id: Optional[str] = None
    content: str
    hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Enhancement layer
    confidence: Optional[float] = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    source_context: Optional[str] = None
    source_session_id: Optional[str] = None
    version_of: Optional[str] = None
    importance: Optional[float] = None
    type: Optional[MemoryType] = None
    subject_ref: Optional[str] = None
    fact_family: Optional[FactFamily] = None
    relation_type: Optional[str] = None
    field_key: Optional[str] = None
    field_value_json: Optional[Dict[str, Any]] = None
    canonical_text: Optional[str] = None
    raw_text: Optional[str] = None

    # Search-only (not persisted)
    score: Optional[float] = None


class HistoryRecord(BaseModel):
    """A single history entry for a memory operation."""

    id: str
    memory_id: str
    user_id: str
    operation: MemoryOperation
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OwnerContext(BaseModel):
    """Identity context for an add/search request."""

    external_user_id: Optional[str] = None
    anonymous_session_id: Optional[str] = None
    display_name: Optional[str] = None
    channel: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OwnerRecord(BaseModel):
    """Resolved owner record stored in the relational backing store."""

    owner_id: str
    owner_type: OwnerType
    external_user_id: Optional[str] = None
    anonymous_session_id: Optional[str] = None
    display_name: Optional[str] = None
    channel: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubjectRecord(BaseModel):
    """Owner-local third-party subject reference."""

    owner_id: str
    subject_ref: str
    relation_type: str
    display_name: Optional[str] = None
    normalized_name: Optional[str] = None
    is_named: bool = False
    created_at: datetime
    updated_at: datetime
    aliases: Dict[str, Any] = Field(default_factory=dict)


class FactEnvelope(BaseModel):
    """Structured fact representation produced before persistence."""

    owner_id: str
    user_id: str
    owner_type: OwnerType
    subject_ref: str
    fact_family: FactFamily
    relation_type: str
    field_key: str
    field_value_json: Dict[str, Any] = Field(default_factory=dict)
    canonical_text: str
    raw_text: str
    confidence: float = 0.5
    source_context: Optional[str] = None
    source_session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
