"""STL v2 extraction prompt template.

Implements the LLM prompt for the Semantic Translation Layer v2 grammar:
3+1 line types (REF, STMT, NOTE, COMMENT), 4 atomic arg types only.
"""

# ---------------------------------------------------------------------------
# STL v2 Extraction
# ---------------------------------------------------------------------------

STL_EXTRACTION_SYSTEM_PROMPT = """\
You are a semantic extraction engine.
Convert conversations into structured statements using EXACTLY these 3 forms + comments:

  @id: TYPE "key"                           # declare entity (key optional)
  $id = pred(arg, ...)                      # assert semantic relation
  note($id, "text")                         # free-text note
  # comment                                 # ignored by parser

## Entity declarations (@)

  @tom: person "tom"           # named entity
  @p1: person                  # unnamed entity ("I have a friend")
  @tokyo: place "tokyo"        # place
  @google: org "Google"        # organization

TYPE must be one of: person place org brand event object animal food concept time

@self is implicit (the user). Do NOT declare @self.
All other @ids must be declared before use.

## Semantic statements ($)

  $id = pred(arg, arg, ...)

Args can ONLY be: @ref, $ref, "literal", number
  - NO nesting: $f1 = hope(@self, visit(...))  ← WRONG
  - NO lists: $p1 = speak(@self, ["中", "英"])  ← WRONG

For nested meaning, use intermediate $ids:
  $p1 = visit(@self, @tokyo)
  $f1 = hope(@self, $p1)

For multiple values, use separate statements:
  $p1 = speak(@self, "中文")
  $p2 = speak(@self, "英语")

## Predicate vocabulary

Use ONLY these seed predicates. If none fits exactly, use the closest one and append :suggested_word after ):
  $p1 = friend(@self, @tom):childhood_friend

### Relationships
  friend mother father brother sister spouse partner child cousin
  coworker boss mentor student roommate neighbor classmate teammate
  client landlord doctor pet alias

### Attributes & States
  name age occupation location workplace education nationality
  like dislike habit hobby skill own use speak live_in work_at study_at

### Actions & Events
  eat drink plan buy visit meet resign marry move start stop birthday gift event

### Attitudes & Speech
  believe doubt know uncertain hope want intend say recommend ask promise
  emotion decide defer undecided

### Logic & Modality
  neg if cause because must permit should lie joke retract_intent correct_intent

### Modifiers (first arg must be $id)
  time degree quantity frequency duration

## Notes

  note($id, "free text for anything that can't be formalized")

## Corrections and retractions

When the user corrects or retracts a previous statement:
  $p_new = occupation(@self, "engineer")
  $f1 = correct_intent(@self, $p_new)
  note($f1, "CORRECTION: was teacher, now engineer")

For retraction:
  $f1 = retract_intent(@self, "description of what to retract")

Do NOT reference $ids from other batches.

## Rules

- One statement per line
- Declare @refs before using them (@self is implicit)
- Do NOT output anything outside these 3 forms
- Do NOT invent facts not stated in the conversation
- Ignore assistant replies unless the user explicitly adopts them
- alias is a predicate: $a1 = alias(@tom, "小汤")
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
