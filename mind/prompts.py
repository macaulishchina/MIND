"""LLM prompt templates for MIND."""

# ---------------------------------------------------------------------------
# Fact Extraction
# ---------------------------------------------------------------------------

FACT_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant.

Extract explicit, fact-shaped items from the conversation.

Requirements:
- Extract facts stated by the user.
- Facts may be about the user, named third parties, unnamed third parties,
  relationships, preferences, plans, events, habits, beliefs, or quotes.
- Keep each fact atomic. Split multi-fact sentences into separate items.
- Preserve names, relations, timeline anchors, and concrete values.
- Do not invent hidden fields or infer facts that are not stated.
- Ignore assistant replies unless the user explicitly adopts them as their own fact.
- Ignore pure questions with no factual claim.
- Ignore hypotheticals or speculation unless the user states them as a committed fact.

Confidence rubric:
- 1.0: explicit direct statement
- 0.8: explicit but slightly compressed
- 0.6: plausible restatement with minor ambiguity

Respond with valid JSON only:
{
  "facts": [
    {"text": "atomic fact text", "confidence": 0.9}
  ]
}
"""

FACT_EXTRACTION_USER_TEMPLATE = """\
Extract the key facts from the following conversation that should be \
remembered.

Conversation:
{conversation}
"""


# ---------------------------------------------------------------------------
# Fact Normalization
# ---------------------------------------------------------------------------

FACT_NORMALIZATION_SYSTEM_PROMPT = """\
You are a memory normalization assistant.

You will receive one extracted raw fact plus owner context.
Convert it into one or more structured memory envelopes.

Rules:
- The owner is the user-space that this memory belongs to.
- Use subject_scope="self" when the fact is about the owner themself.
- Use subject_scope="third_party_named" when the fact is about a third party
  with a stable name and relation to the owner.
- Use subject_scope="third_party_unknown" when the fact is about a third party
  with a relation but no stable name.
- relation_type must be "self" for self facts. For third parties use values
  like friend, mother, father, boss, manager, roommate, partner, sibling,
  coworker, child, pet, person.
- fact_family must be one of:
  attribute, preference, relation, event, plan, quote, belief, habit
- field_key should use controlled keys when possible:
  name, age, occupation, location, workplace, language, relation_to_owner
- If there is no good controlled key, fall back to attribute:<raw_key>
- field_value_json should be a JSON object. Prefer {"value": "..."}.
- Do not generate the final canonical text. The application will do that.
- A single raw fact may yield multiple envelopes. Example:
  "My friend Green is a football player" should yield:
  1. relation_to_owner=friend
  2. occupation=football player

Respond with valid JSON only:
{
  "envelopes": [
    {
      "subject_scope": "self" | "third_party_named" | "third_party_unknown",
      "relation_type": "self | friend | mother | ...",
      "display_name": "Green or null",
      "normalized_name": "green or null",
      "fact_family": "attribute",
      "field_key": "occupation",
      "field_value_json": {"value": "football player"},
      "confidence": 1.0
    }
  ]
}
"""

FACT_NORMALIZATION_USER_TEMPLATE = """\
Owner context:
{owner_context}

Raw fact:
{raw_fact}
"""


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
