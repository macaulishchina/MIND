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


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class MemoryItem(BaseModel):
    """Core memory representation (two-layer design)."""

    # Core layer
    id: str
    user_id: str
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
