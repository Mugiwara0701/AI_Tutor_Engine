"""
equation_intent.py — dynamic educational-intent routing for equations
(ISSUE 3 / ISSUE 4).

Decides whether a given equation should be sent through the expensive
equation_analysis VLM call at all. The rule (per the frozen requirement):

    Run equation_analysis ONLY IF the equation introduces reusable
    knowledge (a Formula Box, Law, Identity, Theorem, Rule, Principle,
    General/Master/Canonical/Named Equation, Reaction Equation, or a
    Definition that introduces new notation).

    Skip it (but NEVER delete the equation itself) when the equation only
    *uses* already-introduced knowledge -- a Worked/Solved Example, an
    Exercise/Homework/Assignment/Activity/Case Study/Numerical
    Problem/Illustration/MCQ/Revision or Previous-Year Question/Model
    Paper/intermediate calculation/substitution step/arithmetic step/
    final answer/unit conversion/solution walkthrough/teacher explanation.

This module is deliberately publisher-agnostic: it does not hardcode
NCERT (or any other publisher's) block labels. It builds on top of two
signals that are already dynamic and subject-agnostic:

  1. modules/stage_b_classify.py's `block_type` -- itself derived from
     generic structural/typographic anchors (label words, an open
     "Example/Solution" span tracked across the page, numeric-
     substitution-vs-pure-variable-form line shape, ...), never from a
     hardcoded per-subject vocabulary.
  2. A small set of INSTRUCTIONAL-VERB / REUSABLE-KNOWLEDGE text cues
     (below) used only as a fallback for block types Stage B could not
     confidently resolve (e.g. "Ambiguous", or an equation-cluster with
     no classified block at all) -- these cues are generic English
     instructional language ("solve", "calculate", "derive", "law of",
     "is defined as", ...), not any specific curriculum's phrasing, so
     the same logic applies whether the source book is NCERT Physics,
     a different publisher's Chemistry book, or a non-Indian curriculum
     entirely.
"""
import re
from typing import Optional

# Stage B block_types that, by construction, introduce reusable knowledge
# (see modules/stage_b_classify.py BLOCK_TYPES / classify()).
REUSABLE_BLOCK_TYPES = {"Formula Box", "Law", "Definition"}

# Stage B block_types that, by construction, only ever *use* previously
# introduced knowledge to solve/practice/review something.
NON_REUSABLE_BLOCK_TYPES = {
    "Worked Example", "Exercise", "Activity", "Reference", "Footer",
    "Header", "Summary",
}

# Fallback text cues, used only when block_type is missing/Ambiguous or
# not in either set above. Generic instructional language, not tied to any
# one publisher's block-naming convention (Issue 4).
_REUSABLE_TEXT_HINTS = re.compile(
    r"\b(law of|principle of|theorem|postulate|identity|general formula|"
    r"master formula|canonical (?:form|equation)|reaction equation|"
    r"is defined as|is given by|is expressed as|named after|rule of)\b",
    re.I,
)
_NON_REUSABLE_TEXT_HINTS = re.compile(
    r"\b(solve|solving|calculate|find the|evaluate|substitut|therefore|"
    r"hence,?\s|answer\s*[:=]|solution\s*[:.]|exercise|practice|homework|"
    r"assignment|numerical problem|case stud|worksheet|revision|"
    r"previous year|model paper|illustration \d|q\d+[.)]|mcq)\b",
    re.I,
)


def introduces_reusable_knowledge(block_type: Optional[str], raw_text: str = "") -> bool:
    """True  -> run the expensive equation_analysis VLM call.
    False -> skip the VLM call, but the caller must still keep every
             deterministic field for the equation (Issue 5)."""
    if block_type in REUSABLE_BLOCK_TYPES:
        return True
    if block_type in NON_REUSABLE_BLOCK_TYPES:
        return False

    # block_type is None/"Ambiguous"/unmapped (e.g. no Stage A/B block
    # matched this exact region) -- fall back to generic instructional
    # text cues rather than defaulting either way blindly.
    text = raw_text or ""
    if _REUSABLE_TEXT_HINTS.search(text):
        return True
    if _NON_REUSABLE_TEXT_HINTS.search(text):
        return False

    # Genuinely unknown: stay conservative and keep running
    # equation_analysis. Issue 3 asks to cut confidently-identified,
    # expensive, low-value calls (solved examples/exercises/...), not to
    # silently under-analyze equations we cannot yet classify at all --
    # doing so would risk dropping real Master JSON semantics (Issue 5/6).
    return True


def skip_reason(block_type: Optional[str], raw_text: str = "") -> str:
    """Human-readable reason string stored on the equation record when
    equation_analysis was skipped, so this decision is auditable in the
    Master JSON rather than silently invisible."""
    if block_type in NON_REUSABLE_BLOCK_TYPES:
        return f"block_type={block_type!r} identified as using (not introducing) knowledge"
    if _NON_REUSABLE_TEXT_HINTS.search(raw_text or ""):
        return "surrounding text matched solved-problem/exercise instructional cues"
    return "classified as not introducing reusable knowledge"
