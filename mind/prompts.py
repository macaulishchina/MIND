"""LLM prompt templates for MIND."""

# ---------------------------------------------------------------------------
# Update Decision
# ---------------------------------------------------------------------------

UPDATE_DECISION_SYSTEM_PROMPT = """\
You decide how one NEW canonical memory fact relates to a short list of
EXISTING canonical memories.

Inputs:
1. EXISTING memories, each shown as [temporary_id] canonical_text
2. NEW fact, already rendered as one canonical_text string

Choose exactly one action:
- ADD: The new fact is a distinct memory that should be stored separately.
- UPDATE: One existing memory is the same memory slot, and the new fact is the
  better replacement.
- DELETE: One existing memory should be removed with no replacement text kept.
- NONE: The new fact is already covered, already implied by a stricter
  existing memory, or not worth storing.

Decision rules:
- Compare subject and field first. The best match usually shares the same
  [subject] prefix and the same field key before '='.
- Choose NONE when an existing memory already says the same thing or a more
  complete version of the same thing.
- Choose UPDATE when exactly one existing memory clearly represents the same
  subject and field, and the new fact is newer, more specific, corrected, or
  otherwise the better replacement.
- Choose ADD when the new fact is about a different subject, a different field,
  or a separate fact that should coexist.
- Choose DELETE only for a clear contradiction where no replacement text
  should remain. If the new fact provides the replacement value, prefer UPDATE
  instead of DELETE.
- If multiple memories look similar, choose the single best temporary id. Do
  not reference an id from a different subject just because the value wording
  is similar.

ID rules:
- Use only the provided temporary ids exactly as shown.
- For ADD and NONE, set "id" to null.
- For UPDATE and DELETE, set "id" to one provided temporary id.

Text rules:
- For ADD, "text" must be the one canonical memory string to store.
- For UPDATE, "text" must be the one canonical memory string that should
  replace the target memory.
- Preserve canonical format: "[subject] field=value".
- Preserve the correct subject prefix from the new fact unless one listed
  memory proves that the replacement must stay on another subject.
- Do not output multiple memories, bullet lists, markdown, or explanation text
  inside "text".
- For DELETE and NONE, set "text" to "".

Tie-breakers:
- Same subject + same field beats same subject only.
- Same subject only beats similar wording with a different subject.
- Exact duplicate or strictly subsumed fact -> NONE.
- One clear replacement memory slot -> UPDATE.
- Uncertain and distinct -> ADD.

Respond with JSON only:
{
  "action": "ADD" | "UPDATE" | "DELETE" | "NONE",
  "id": null | "temporary_id",
  "text": "canonical memory text for ADD/UPDATE, otherwise empty string",
  "reason": "brief explanation of your decision"
}

Canonical example:
Existing memories:
[0] [self] attribute:favorite_season=spring

New fact: [self] attribute:favorite_season=late spring

Response:
{"action":"UPDATE","id":"0","text":"[self] attribute:favorite_season=late spring","reason":"same subject and field, newer replacement"}
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
