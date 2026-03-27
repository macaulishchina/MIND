"""LLM prompt templates for MIND.

Two core prompts:
1. FACT_EXTRACTION_PROMPT — extracts facts with confidence from conversations
2. UPDATE_DECISION_PROMPT — decides ADD/UPDATE/DELETE/NONE for each fact

Design notes:
- Confidence scoring is MIND's key enhancement over mem0's extraction prompt
- Temporary IDs in the update prompt prevent LLM UUID hallucination (mem0 trick)
- source_context is captured from the original conversation, not generated here
"""

# ---------------------------------------------------------------------------
# Fact Extraction
# ---------------------------------------------------------------------------

FACT_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Your job is to extract factual
information from conversations that would be useful to remember for future
interactions with this user.

Focus on extracting:
- Personal preferences (food, music, hobbies, etc.)
- Personal information (name, location, job, family, etc.)
- Plans and goals (upcoming events, projects, aspirations)
- Health and wellness information
- Professional details (job role, skills, workplace)
- Opinions and beliefs
- Important events and experiences
- Relationships and social connections

For each extracted fact, also assess your confidence level (0.0 to 1.0):
- 1.0: Explicitly and clearly stated by the user ("I am a software engineer")
- 0.8: Strongly implied with clear context ("I've been coding Python for 10 years at Google")
- 0.5: Reasonably inferred but could be misinterpreted
- 0.3: Weakly implied or uncertain ("If I ever go to Japan...")
- 0.1: Very speculative

Rules:
- Extract only facts about the USER, not about other people unless directly relevant
- Pay attention to tense and context — distinguish past from present
- Do NOT extract hypotheticals or conditional statements as facts
- Do NOT extract the AI assistant's responses as user facts
- Each fact should be a single, concise statement
- Return an empty list if no memorable facts are found

Respond in JSON format:
{
  "facts": [
    {"text": "fact description", "confidence": 0.9},
    {"text": "another fact", "confidence": 0.7}
  ]
}
"""

FACT_EXTRACTION_USER_TEMPLATE = """\
Extract the key facts from the following conversation that should be \
remembered about the user.

Conversation:
{conversation}
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
