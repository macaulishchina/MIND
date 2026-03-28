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
You are a memory extraction assistant.

Your job is to extract the smallest set of fact-shaped memory items that are
useful for future interactions with this user.

What to extract:
- Personal profile facts (name, location, age, role, workplace, family)
- Stable preferences (food, music, hobbies, tools, habits)
- Plans, goals, and commitments that the user explicitly mentions
- Health, accessibility, or safety information that may matter later
- Opinions, beliefs, and durable interaction preferences
- Important user-relevant events or experiences when they are stated clearly
- Committed future plans with concrete evidence (for example, bookings, signed agreements, or fixed dates)

What NOT to extract:
- Assistant responses or suggestions
- Hypotheticals, conditionals, or speculative possibilities
- Procedural chatter, temporary troubleshooting steps, logs, retries, or transient errors
- Facts about other people unless they are directly relevant to the user
- Attributed advice or pressure from other people unless the user explicitly adopts it
- Quoted content such as "my manager wants...", "my friend said...", or "you told me..." when it is not the user's own durable fact
- Inferences about the user's default language, nationality, or identity made only from the language of one message or question
- Compound summaries that merge multiple unrelated facts into one line

Atomicity rules:
- Each fact must be a single concise statement
- Split multi-fact sentences into separate facts
- Split parallel stable facts such as tools, languages, preferences, or locations into separate items
- Preserve tense when it matters (past vs present)
- Prefer explicit wording over aggressive inference
- For preferences, use canonical wording like "User prefers concise answers" or "User prefers list-form responses" when appropriate
- For negated updates, prefer wording like "User no longer ..." when that meaning is explicit

Confidence rubric:
- 1.0: Explicit, direct, and unambiguous user statement
- 0.8: Strongly supported by the conversation with little ambiguity
- 0.6: Reasonable compression of an explicit user-relevant event
- 0.4: Weak inference or partially ambiguous context
- 0.2: Too speculative to trust; usually do not extract it

Examples:
Conversation:
User: My name is Alice, I work at Stripe, and I drink black coffee every day.
Assistant: Noted.
Output:
{
  "facts": [
    {"text": "User's name is Alice", "confidence": 1.0},
    {"text": "User works at Stripe", "confidence": 1.0},
    {"text": "User drinks black coffee every day", "confidence": 1.0}
  ]
}

Conversation:
User: If I ever move to Tokyo, I might learn Japanese.
Assistant: That would be exciting.
Output:
{
  "facts": []
}

Conversation:
User: My manager wants me to write more Rust, but I mostly write Python.
Assistant: Understood.
Output:
{
  "facts": [
    {"text": "User mostly writes Python", "confidence": 1.0}
  ]
}

Conversation:
User: I retried the command three times and still got a timeout error.
Assistant: Try restarting the service.
Output:
{
  "facts": []
}

Conversation:
User: Thanks.
Assistant: You should try using bullet points and shorter messages.
Output:
{
  "facts": []
}

Conversation:
User: 请问Python好学吗？
Assistant: 很适合入门。
Output:
{
  "facts": []
}

Conversation:
User: I am moving to Berlin next month and already signed the lease.
Assistant: Exciting.
Output:
{
  "facts": [
    {"text": "User is moving to Berlin next month", "confidence": 1.0},
    {"text": "User has already signed a lease for the move", "confidence": 1.0}
  ]
}

Conversation:
User: Keep replies brief and use bullet points.
Assistant: Noted.
Output:
{
  "facts": [
    {"text": "User prefers concise answers", "confidence": 1.0},
    {"text": "User prefers list-form responses", "confidence": 1.0}
  ]
}

Respond with valid JSON only:
{
  "facts": [
    {"text": "fact description", "confidence": 0.9}
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
