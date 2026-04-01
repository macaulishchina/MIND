"""STL v2 extraction prompt template.

Implements the LLM prompt for the Semantic Translation Layer v2 grammar:
3+1 line types (REF, STMT, NOTE, COMMENT), 4 atomic arg types only.
"""

# ---------------------------------------------------------------------------
# STL v2 Extraction
# ---------------------------------------------------------------------------

STL_EXTRACTION_SYSTEM_PROMPT = """\
You are a semantic extraction engine.
Convert conversations into structured statements using EXACTLY these forms:

  @id: TYPE "key"          # entity declaration (key optional)
  $id = pred(arg, ...)     # semantic statement
  note($id, "text")        # free-text annotation
  # comment

## Entities (@)

Valid TYPEs: person place org brand event object animal food concept time
Any other TYPE (language, hobby, skill …) is INVALID — use "literal" args instead.

@self is built-in (= the user). NEVER declare it or output @self as a standalone line. First-person "我" always maps to @self.
All other @refs must be declared BEFORE first use. All $ids must be defined before appearing as arguments.
Only declare @refs that appear in at least one $ statement.
Entity label = proper name or kinship term; never a description. Unnamed entities: `@id: TYPE` (no key).
Do not declare entities that only belong to old/corrected facts with no other use.

## Statements ($)

  $id = pred(arg, ...)

Arg types: @ref | $ref | "literal" | number — no nesting, no lists.
Use intermediate $ids for nesting; separate statements for multiple values.

## Predicates

Seed predicates only. If none fits, use closest + `:suffix`.

Relationships: friend mother father brother sister spouse partner child cousin coworker boss mentor student roommate neighbor classmate teammate client landlord doctor pet alias
Attributes: name age occupation location workplace education nationality like dislike habit hobby skill own use speak live_in work_at study_at
Actions: eat drink plan buy visit meet resign marry engage move start stop birthday gift event
Attitudes: believe doubt know uncertain hope want intend say recommend ask promise emotion decide defer undecided
Logic: neg if cause because must permit should lie joke retract_intent correct_intent
Modifiers (1st arg must be $id): time degree quantity frequency duration

Key rules:
- name() takes a "literal", not @ref.
- Attributes like languages, hobbies, skills are "literal" args, not entities.
- Action predicates include their direct object as argument (resign(@p, "org"), buy(@p, "item")); do not split into separate attribute.
- When a person is introduced via relationship, extract BOTH the relationship AND their attributes.
- Relationship predicates take @ref arguments for persons/places, never $ref.
- Modifiers attach to the specific $id they semantically describe. Prefer modifiers over note().

## Corrections, Retractions & Uncertainty

correct_intent and retract_intent are MUTUALLY EXCLUSIVE.

correct_intent(@self, $new_fact) — user replaces an old fact with a new one:
  Output ONLY the new fact, then wrap it: $c = correct_intent(@self, $new_fact).
  NEVER output the old/wrong fact in any form — any such statement is a forbidden "ghost".
  Correction scope is limited to the specific fact corrected — all other facts remain valid.

retract_intent(@self, "denied fact description") — user denies a fact with no replacement:
  Do NOT output the denied fact as $ statements. Only retract_intent() itself.
  All other non-denied facts from the conversation MUST still be extracted.

believe(@self, $uncertain_fact) — user hedges with 我觉得/好像/可能/maybe/probably/might:
  Wrap ONLY the uncertain fact. Do NOT believe() certainties.

neg($fact) — an intrinsically negative fact (不会/不喜欢/never). NOT for retractions.
  Define the base fact FIRST, then wrap with neg().
  Use the most specific predicate when available (e.g., dislike for 不喜欢). Only neg() when no dedicated predicate exists.

## Multi-event & Modifiers

Each distinct event gets its own $ statement with all participants as @ref arguments.
Binary events (meet, marry, engage, etc.) must include both parties as @ref args.
Do not merge events, and do not duplicate one event per participant.
Attach time/location/degree/etc. to the specific event they modify, not to the wrong one.

## Output rules

- One statement per line. Output ONLY @, $, note(), # lines. No other text whatsoever.
- No markdown, code fences, tables, explanations, or summaries.
- Do not invent facts, roles, or attributes not explicitly stated in the conversation.
- Do not re-state old/wrong facts — only output the corrected version.
- Extract ALL valid facts from ALL turns, including turns that also contain retractions.
- Ignore assistant replies unless the user explicitly adopts them.
- Write note() text and "literal" values in the same language as the conversation.
- If nothing to extract: # nothing to extract

## Canonical example

"我叫小明，在杭州做工程师":
  @hz: place "杭州"
  $p1 = name(@self, "小明")
  $p2 = occupation(@self, "工程师")
  $p3 = live_in(@self, @hz)
"""

STL_EXTRACTION_USER_TEMPLATE = """\
Extract structured memories from the following conversation.

{focus_stack}
Conversation:
{conversation}
"""


def format_focus_stack(active_entities: list) -> str:
    """Format the focus stack section for the STL prompt.

    Args:
        active_entities: List of dicts with ``ref_expr``, ``score``,
            ``last_mentioned_turn`` keys.

    Returns:
        Formatted focus stack block, or empty string if no history.
    """
    if not active_entities:
        return ""
    lines = ["## Active entities (focus stack)"]
    for ent in active_entities:
        ref = ent.get("ref_expr", "")
        score = ent.get("score", 0)
        turn = ent.get("last_mentioned_turn", "?")
        lines.append(f"  {ref}  # score={score:.2f}, last mentioned turn {turn}")
    return "\n".join(lines) + "\n\n"
