"""LLM prompt templates for MIND."""

# ---------------------------------------------------------------------------
# Update Decision
# ---------------------------------------------------------------------------

UPDATE_DECISION_SYSTEM_PROMPT = """\
You are a memory management assistant. You will be given:
1. A list of EXISTING memories (each with a temporary ID)
2. A NEW fact that was just extracted from a conversation

Your job is to decide what to do with the new fact relative to the existing
memories. Choose exactly ONE action:

- **ADD**: The fact is genuinely new information not covered by any existing
  memory. Create a new memory.
- **UPDATE**: The fact updates, refines, or supersedes an existing memory.
  An existing memory covers the same concept but the new fact has more detail,
  more recent information, or corrects the old one. Provide the ID of the
  memory being updated and the new combined text.
- **DELETE**: The new fact directly contradicts an existing memory and the
  existing memory should be removed. Provide the ID of the memory to delete.
- **NONE**: The fact is already fully captured by an existing memory, or it
  is not worth remembering. No action needed.

Guidelines:
- Prefer UPDATE over ADD when an existing memory covers the same topic
- Prefer UPDATE over DELETE when information evolved (e.g., preference changed)
- Only use DELETE when there is a clear, direct contradiction
- Use temporary IDs (0, 1, 2, ...) — never fabricate UUIDs

Respond in JSON format:
{
  "action": "ADD" | "UPDATE" | "DELETE" | "NONE",
  "id": null | "temporary_id",
  "text": "the memory text to store (for ADD and UPDATE)",
  "reason": "brief explanation of your decision"
}
"""

UPDATE_DECISION_USER_TEMPLATE = """\
Existing memories:
{existing_memories}

New fact: {new_fact}

Decide what action to take.
"""


def format_existing_memories(memories: list) -> str:
    """Format existing memories with temporary IDs for the update prompt.

    Args:
        memories: List of dicts with at least 'id' and 'content' keys.

    Returns:
        Formatted string with temporary IDs.
    """
    if not memories:
        return "(no existing memories)"

    lines = []
    for idx, mem in enumerate(memories):
        content = mem.get("content", mem.get("payload", {}).get("content", ""))
        lines.append(f"[{idx}] {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt Registry — auto-populated on import
# ---------------------------------------------------------------------------
# Maps ``id(prompt_string)`` → variable name for all module-level variables
# whose name ends with ``_SYSTEM_PROMPT``.  This allows ``BaseLLM.generate()``
# to auto-detect which prompt template was used without explicit parameters.

import sys as _sys

PROMPT_REGISTRY: dict[int, str] = {
    id(v): k
    for k, v in vars(_sys.modules[__name__]).items()
    if k.endswith("_SYSTEM_PROMPT") and isinstance(v, str)
}
