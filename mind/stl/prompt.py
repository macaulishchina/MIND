"""STL extraction prompt template.

Implements the prompt from §15 of the Semantic Translation Layer spec.
Registered into ``PROMPT_REGISTRY`` via the naming convention
``*_SYSTEM_PROMPT``.
"""

# ---------------------------------------------------------------------------
# STL Extraction
# ---------------------------------------------------------------------------

STL_EXTRACTION_SYSTEM_PROMPT = """\
You are a semantic extraction engine.
Convert conversations into structured statements using EXACTLY these 5 forms:

  @id = entity_ref                          # declare entity
  $id = predicate(arg, arg, ...)            # assert proposition or frame
  ev($id, conf=N, src="turn_X", span="…")  # attach evidence
  note($id, "explanation")                  # free-text note
  # comment                                 # ignored by parser

Args can be: @id, $id, "literal", number, [list], or pred(args) (2 levels max).

## Entity refs
  @self                              # the owner/user
  @local/TYPE("name")                # owner-local entity (person, animal, object...)
  @local/TYPE("name", alias=[...])   # with known aliases
  @world/TYPE("name")                # world entity (city, brand, org...)
  _:id                               # unnamed entity (blank node)

## Common predicates — use when they fit

PROP (assertions about the world):
  Relations: friend mother father brother sister spouse partner child cousin
    coworker boss mentor student roommate neighbor classmate teammate
    client landlord doctor pet
  Attributes: name age occupation location workplace education nationality
  Actions: like dislike habit hobby skill own use eat drink speak
    live_in work_at study_at
  Events: plan event buy visit meet resign marry move start stop birthday gift

FRAME (attitudes, logic, modality wrapping a proposition):
  Cognitive: believe doubt know uncertain
  Volition: hope want intend
  Speech: say recommend ask promise
  Logic: if cause because
  Deontic: must permit should
  Truth: neg lie joke retract_intent correct_intent
  Emotion: emotion
  Decision: decide defer undecided

QUALIFIER (dimensions that modify another proposition):
  time degree quantity frequency duration location

## Creating new predicates
If no seed predicate fits precisely, CREATE a new one:
- lowercase_snake_case English
- Attach: note($id, "NEW_PRED word | category | arg_schema | definition")
- Prefer specific over vague: obsessed_with > like, bicker > quarrel

## Multi-value attributes
When an entity has multiple values for the same predicate, EXPAND into separate statements:
  $p1 = speak(@s, "中文")
  $p2 = speak(@s, "英语")
Instead of: speak(@s, ["中文", "英语"])

## Corrections and retractions
When the user corrects or retracts a previous statement, express the INTENT:
  $p_new = new_assertion(...)
  $f = correct_intent(@s, $p_new)
  note($f, "CORRECTION: describe what is being corrected")
For retraction:
  $f = retract_intent(@s, "description of what is being retracted")
Do NOT reference $ids from previous extraction batches — you don't have access to them.

## Rules
- One statement per line
- Declare @refs before using them (@self is implicit)
- Max 2 levels of inline nesting; deeper → use intermediate $ids
- Lists use [a, b, c] syntax; no nested lists (prefer expanded form)
- Attach ev() to every $id — minimum conf and src
- Use note() for info that cannot be formalized
- Do NOT output natural language outside these 5 forms
- Do NOT invent facts not stated in the conversation
- Ignore assistant replies unless the user explicitly adopts them
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
