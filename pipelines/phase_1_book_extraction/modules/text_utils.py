"""
modules/text_utils.py — M4.1A: Shared Text Pattern Infrastructure.

Single authoritative source for pattern constants and utility functions used
by multiple pipeline modules.  This module consolidates definitions that were
previously duplicated across stage_a_geometry.py and content_blocks.py, and
introduces new patterns approved by the frozen M4.1 architecture.

SCOPE RULES (enforced, not aspirational):
  - No pipeline logic.
  - No recognizer logic.
  - No imports from any pipeline stage or recognizer.
  - Pure deterministic Python.
  - No I/O.
  - No external dependencies (stdlib re and typing only).

Consumers (as of M4.1A):
  stage_a_geometry.py   — DEFINITION_TERM_*_RE, TERM_STOPWORDS
  content_blocks.py     — DEFINITION_TERM_*_RE, TERM_STOPWORDS
  (later M4.1 milestones will add: recognizers, copyright_sanitizer)

Design notes
------------
DEFINITION_TERM_FIRST_RE and DEFINITION_TERM_AFTER_RE are preserved byte-for-
byte from the originals in stage_a_geometry.py / content_blocks.py (which were
already identical to each other).  Any change to these patterns is a separate
architectural decision, not part of M4.1A scope.

DEFINITION_TERM_DENOTES_RE restricts the term to a capital-initial token to
reduce false positives in explanatory prose ("acceleration denotes...").

DEFINITION_TERM_BY_MEAN_RE uses re.I so "by X we mean" and "By X We Mean" both
match; the capital constraint inside the pattern is therefore relaxed relative
to DENOTES_RE.

STEP_MARKER_RE: the frozen M4.1 architecture specifies a trailing \\b after the
full alternation group.  In practice, \\b after the punctuation alternatives
'[0-9]+[.)]' and '[a-z][.)]' fails when followed by a space (the most common
case: "1. Do this"), because both '.' / ')' and ' ' are \\W — there is no word
boundary between two non-word characters.  The existing _STEP_RE in
procedure_recognizers.py already handles this correctly by applying no trailing
anchor after punctuation alternatives.  STEP_MARKER_RE follows the same
approach: \\b is applied per-alternative, only where it is semantically correct
(word-initial markers like 'step\\s*\\d+', 'first', 'then', etc.).  The
punctuation alternatives rely on the leading '^\\s*' anchor for specificity.
This is a deliberate implementation decision, not a deviation from the
architecture's intent.
"""
from __future__ import annotations

import re
from typing import Union

# ---------------------------------------------------------------------------
# Definition sentence patterns
# ---------------------------------------------------------------------------

# "X is defined as ..."
# Requires the term to begin with a capital letter followed by at least one
# more letter, giving a minimum term length of 3 characters.  Intentionally
# NOT re.I — the capital-initial requirement is the primary quality signal.
#
# Preserved verbatim from stage_a_geometry._DEFINITION_TERM_FIRST_RE and
# content_blocks.DEFINITION_TERM_FIRST_RE (both were identical).
DEFINITION_TERM_FIRST_RE: re.Pattern = re.compile(
    r"^(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,38})\s+(?:is|are)\s+defined as\b"
)

# "... is called X" / "... is known as X" / "... is referred to as X"
# Uses re.I so the connector words match regardless of case.  The term capture
# uses a lazy quantifier {1,38}? combined with a lookahead so that the term
# ends at a natural sentence boundary (punctuation, 'and', end-of-line) rather
# than greedily consuming trailing words.
#
# The optional article prefix (the\s+ | an?\s+) is intentional: it lets the
# pattern absorb leading articles so they do not become part of the captured
# term.  However it can backtrack if the article is the last word on the line
# and the real term is on the next line — this is a known limitation documented
# in the original content_blocks.py, and is filtered downstream by term_is_valid().
#
# Preserved verbatim from stage_a_geometry._DEFINITION_TERM_AFTER_RE and
# content_blocks.DEFINITION_TERM_AFTER_RE (both were identical).
DEFINITION_TERM_AFTER_RE: re.Pattern = re.compile(
    r"\b(?:is|are)\s+(?:called|known as|referred to as)\s+"
    r"(?:the\s+|an?\s+)?(?P<term>[A-Za-z][A-Za-z \-]{1,38}?)(?=[.,;:]|\s+and\b|$)",
    re.I,
)

# "X denotes ..." — capital-initial term only.
# re.I is NOT applied so that lowercase "osmosis denotes..." does not match.
# "refers to" was evaluated and rejected: it fires too broadly in explanatory
# prose ("The acceleration refers to the rate of change of velocity" is
# explanatory, not a definition) — see frozen M4.1 architecture R-I2 decision.
DEFINITION_TERM_DENOTES_RE: re.Pattern = re.compile(
    r"\b(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,38})\s+denotes?\b"
)

# "By X we mean ..." — re.I applied because the phrase is equally common in
# sentence-initial and mid-sentence positions.  Capital constraint is embedded
# in the character class [A-Z] which, with re.I, also matches lowercase — this
# is intentional (the pattern is specific enough that case restriction is not
# needed for precision).
DEFINITION_TERM_BY_MEAN_RE: re.Pattern = re.compile(
    r"\bby\s+(?P<term>[A-Z][A-Za-z][A-Za-z \-]{1,38})\s+we\s+mean\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Term quality — stopwords
# ---------------------------------------------------------------------------

# Unified stopword set from stage_a_geometry._DEFINITION_TERM_STOPWORDS and
# content_blocks._TERM_STOPWORDS (both contained the base set; the extended
# set was approved by the frozen M4.1 architecture R-I3).
#
# Base set (both originals): the, a, an, this, that, these, those, it, its,
#   which, who
# Extended (M4.1 R-I3): given, such, each, every, said, same, other
#
# frozenset is used so this constant cannot be accidentally mutated at runtime.
TERM_STOPWORDS: frozenset = frozenset({
    # base set — preserved from both originals
    "the", "a", "an", "this", "that", "these", "those",
    "it", "its", "which", "who",
    # extended set — added by M4.1 R-I3
    "given", "such", "each", "every", "said", "same", "other",
})

# ---------------------------------------------------------------------------
# Term quality — validation helper
# ---------------------------------------------------------------------------

def term_is_valid(term: str) -> bool:
    """Return True when *term* passes all structural quality checks.

    Centralises the quality filter previously implemented inline in
    stage_a_geometry._definition_candidate_blocks and in
    content_blocks.detect_definition_terms, with the additions approved by
    frozen M4.1 architecture R-I3.

    Rules (all must pass):
      - term is non-empty
      - term is at least 2 characters long  (single characters are noise)
      - term does not start with a digit    (numeric artefacts)
      - term (lowercased) is not in TERM_STOPWORDS
      - term has at most 6 words            (over-long terms are extraction errors)

    The caller is responsible for stripping the term before passing it in.
    """
    if not term:
        return False
    if len(term) < 2:
        return False
    if re.match(r"^\d", term):
        return False
    if term.lower() in TERM_STOPWORDS:
        return False
    if len(term.split()) > 6:
        return False
    return True


# ---------------------------------------------------------------------------
# Step-marker pattern
# ---------------------------------------------------------------------------

# Unified step-marker pattern covering both numbered/lettered bullets and prose
# markers.  Consolidates:
#   procedure_recognizers._STEP_RE       (step\s*\d+, [0-9]+[.)], [a-z][.)])
#   copyright_sanitizer._STEP_N_RE       (step\s*\d+)
#   copyright_sanitizer._NUMBERED_RE     ([0-9]+[.)])
#   copyright_sanitizer._FIRST_RE        (first(?:ly)?)
#   copyright_sanitizer._THEN_RE         (then)
#   copyright_sanitizer._NEXT_RE         (next)
#   copyright_sanitizer._FINALLY_RE      (finally)
#   [architecture addition]              (lastly)
#
# Design note — \b placement:
#   The frozen M4.1 architecture specifies a single trailing \b after the full
#   alternation group.  In Python regex, \b after '.' or ')' (both \W) fails
#   when the next character is a space (also \W), because a word boundary
#   requires one \w and one \W side.  The most common step format "1. Do this"
#   would therefore NOT match with a trailing \b.  The existing _STEP_RE in
#   procedure_recognizers.py correctly omits \b after punctuation alternatives.
#   STEP_MARKER_RE follows the same approach: \b is applied per-alternative,
#   only on word-initial alternatives where it prevents mid-word false matches.
#   Punctuation alternatives rely on the '^\\s*' line-start anchor for
#   specificity.
#
#   This is a documented implementation decision, not a deviation from the
#   architecture's intent.  The architecture's trailing-\b description was
#   schematic; this implementation produces the intended behaviour.
#
# Flags: re.IGNORECASE so "FIRST", "Step 1", "A." all match.
STEP_MARKER_RE: re.Pattern = re.compile(
    r"^\s*(?:"
    r"step\s*\d+\b"         # "Step 1", "step1", "STEP 2:"
    r"|[0-9]+[.)]"          # "1." "1)" "12." — no \b: . and ) are \W
    r"|[a-z][.)]"           # "a." "a)" "B." — no \b: . and ) are \W
    r"|first(?:ly)?\b"      # "First", "Firstly"
    r"|then\b"              # "Then"
    r"|next\b"              # "Next"
    r"|finally\b"           # "Finally"
    r"|lastly\b"            # "Lastly"
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Confidence utility
# ---------------------------------------------------------------------------

def partial_match_confidence(matched: int, total: int, base: float) -> float:
    """Compute a confidence value proportional to the fraction of lines matched.

    Intended for multi-line block recognizers (e.g. GeneralFormulaRecognizer)
    that previously returned a fixed confidence regardless of how many lines
    in the block satisfied the matching criterion.

    Args:
        matched: number of lines (or items) that satisfied the criterion.
        total:   total number of lines (or items) in the block.
        base:    the confidence that would be returned if ALL lines matched.

    Returns:
        0.0                                     if total == 0 or matched == 0
        base                                    if matched == total
        max(base * 0.5, base * matched / total) otherwise

    The floor of base * 0.5 ensures a partial match never produces a
    confidence indistinguishable from zero — it signals "something was found,
    but not conclusively" rather than "nothing was found".

    Examples (base=0.85):
        matched=5, total=5  →  0.85   (all lines match)
        matched=3, total=5  →  0.51   (ratio 0.51 > floor 0.425)
        matched=1, total=5  →  0.425  (ratio 0.17 < floor; floor returned)
        matched=0, total=5  →  0.0
        matched=0, total=0  →  0.0
    """
    if total == 0:
        return 0.0
    if matched == 0:
        return 0.0
    if matched == total:
        return base
    ratio = base * matched / total
    floor = base * 0.5
    return max(floor, ratio)
