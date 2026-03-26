"""Utility functions for MIND."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def generate_id() -> str:
    """Generate a unique memory ID (UUID format, required by Qdrant)."""
    return str(uuid.uuid4())


def generate_hash(content: str) -> str:
    """Generate MD5 hash for deduplication."""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def get_utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def parse_messages(messages: List[Dict[str, str]]) -> str:
    """Parse a list of chat messages into a formatted conversation string.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
            Example: [{"role": "user", "content": "Hello"}, ...]

    Returns:
        Formatted conversation string.
    """
    formatted_lines = []
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        formatted_lines.append(f"{role}: {content}")
    return "\n".join(formatted_lines)
