"""
modules/json_repair.py — a production-grade, model-agnostic JSON repair
pipeline.

Why this exists
----------------
prompt_manager/adapters/qwen_adapter.py already implements a set of
Qwen-specific repairs (markdown-fence stripping, trailing commas, control
characters, truncation, one specific stray-brace shape, one specific
extra-data/duplication shape). Those are all KEPT UNCHANGED — this module
adds a broader, general-purpose second line of defense that:

  1. Handles malformation classes the adapter-specific repairs don't
     attempt (unbalanced braces/brackets, missing colons, single/smart
     quotes, multiple concatenated JSON objects, broken LaTeX commands,
     mixed OCR+LaTeX noise, chemistry/physics notation, unicode math
     symbols, superscript/subscript markers, ...).
  2. Validates with `json.loads` after EVERY individual repair stage
     (never a single big cleanup pass) so a fix that already worked is
     never needlessly followed by another, riskier one.
  3. Is reusable by ANY model adapter, not just Qwen's — so a future
     adapter for a different backend gets the same robustness for free by
     calling `repair_and_parse()` instead of re-implementing all of this.

This module never talks to a model and never raises: every public
function either returns a repaired string / parsed value, or None /
the original input unchanged, so callers can always safely fall through.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("ncert_pipeline.json_repair")


# ===========================================================================
# Stage 1 — strip wrapping noise (markdown fences, prose, multiple objects)
# ===========================================================================
_MD_FENCE_ANYWHERE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)\s*```")
_MD_FENCE_EDGE_RE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$", re.MULTILINE)

_SMART_QUOTES = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2018": "'", "\u2019": "'", "\u2032": "'", "\u2033": '"',
}


def strip_markdown_fences(text: str) -> str:
    """Removes ```json ... ``` / ``` ... ``` fences, whether they wrap the
    whole response or are embedded mid-string (e.g. "explanation ```json
    {...} ``` trailing note"). Falls back to the simple edge-only strip
    when no fenced block is found, so plain unfenced text is untouched."""
    m = _MD_FENCE_ANYWHERE_RE.search(text)
    if m:
        return m.group(1).strip()
    return _MD_FENCE_EDGE_RE.sub("", text).strip()


def _iter_balanced_spans(text: str, open_ch: str, close_ch: str) -> List[Tuple[int, int]]:
    """Finds every top-level [start, end) span that is balanced w.r.t.
    open_ch/close_ch, correctly ignoring braces/brackets that appear
    inside string literals (so a LaTeX '{' inside a JSON string value
    never throws off the scan)."""
    spans = []
    depth = 0
    start = None
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == open_ch:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_ch:
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    spans.append((start, i + 1))
                    start = None
    return spans


def extract_json_candidates(text: str) -> List[str]:
    """Returns every top-level balanced {...} or [...] span found in
    `text`, in order of appearance. Used both to pull JSON out of prose
    ("Sure, here's the JSON: {...}. Hope that helps!") and to separate
    multiple JSON objects the model may have emitted back to back."""
    candidates: List[Tuple[int, str]] = []
    for start, end in _iter_balanced_spans(text, "{", "}"):
        candidates.append((start, text[start:end]))
    for start, end in _iter_balanced_spans(text, "[", "]"):
        # Only keep an array candidate if it isn't already fully contained
        # inside an object candidate we already found (avoids duplicating
        # a nested "key": [...] as if it were its own top-level document).
        if not any(o_start <= start and end <= o_start + len(o_text)
                   for o_start, o_text in candidates):
            candidates.append((start, text[start:end]))
    candidates.sort(key=lambda pair: pair[0])
    return [c for _, c in candidates]


def pick_best_json_object(text: str) -> Optional[str]:
    """When the raw text contains prose + JSON, or several JSON objects
    concatenated/duplicated, this picks the single best candidate: the
    first one that parses cleanly on its own, falling back to the
    longest candidate (most likely to be the "real" answer rather than a
    fragment) if none parse outright. Returns None if no {...}/[...] span
    exists at all."""
    candidates = extract_json_candidates(text)
    if not candidates:
        return None
    for c in candidates:
        try:
            json.loads(c)
            return c
        except json.JSONDecodeError:
            continue
    return max(candidates, key=len)


def remove_duplicated_json_blocks(text: str) -> str:
    """If the exact same JSON object appears more than once (a known VLM
    repetition failure mode — the model answers, then keeps generating
    and repeats itself verbatim), collapse to a single copy."""
    candidates = extract_json_candidates(text)
    if len(candidates) < 2:
        return text
    seen = set()
    deduped = []
    for c in candidates:
        key = re.sub(r"\s+", "", c)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    if len(deduped) == 1:
        return deduped[0]
    return text


# ===========================================================================
# Stage 2 — structural repairs (braces/brackets/quotes/commas/colons)
# ===========================================================================
def balance_braces_and_brackets(text: str) -> str:
    """Closes any unclosed {/[ (in last-opened-first order) and drops any
    stray, unmatched trailing }/] that has nothing to close — a
    meaning-preserving structural repair that never touches string
    content. Skips over string literals so quoted braces/brackets are
    never counted."""
    stack: List[str] = []
    out = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}
    closers = {"}", "]"}
    for ch in text:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            continue
        if ch in pairs:
            stack.append(pairs[ch])
            out.append(ch)
        elif ch in closers:
            if stack and stack[-1] == ch:
                stack.pop()
                out.append(ch)
            # else: stray closer with nothing open — drop it silently,
            # rather than emit a closer that can only produce "Extra data"
            # or mismatched nesting further down the string.
        else:
            out.append(ch)
    if in_string:
        out.append('"')
    out.extend(reversed(stack))
    return "".join(out)


# A raw newline/tab/other control byte appearing inside a string literal.
_CONTROL_CHAR_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def repair_control_characters(text: str) -> str:
    """Escapes raw control characters found inside a JSON string literal
    (json.loads rejects these outright). Generalized copy of the same
    logic qwen_adapter._repair_control_characters implements, kept here
    too so any adapter can reuse it without importing qwen_adapter."""
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch in _CONTROL_CHAR_ESCAPES:
                out.append(_CONTROL_CHAR_ESCAPES[ch])
                continue
            if ord(ch) < 0x20:
                continue  # drop other stray control bytes, no meaningful content
            out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def normalize_smart_quotes(text: str) -> str:
    """Replaces curly/smart quotes with plain ASCII quotes. OCR + some VLM
    decoders occasionally emit typographic quotes inside otherwise-valid
    JSON, which json.loads treats as ordinary (non-delimiting) characters
    -- harmless inside string content, but fatal when they replace an
    actual structural quote around a key or value."""
    for bad, good in _SMART_QUOTES.items():
        text = text.replace(bad, good)
    return text


_SINGLE_QUOTED_KEY_RE = re.compile(r"'([^'\"\n]+?)'\s*:")
_SINGLE_QUOTED_VAL_RE = re.compile(r":\s*'([^'\n]*?)'(?=\s*[,}\]])")


def repair_single_quotes(text: str) -> str:
    """Converts Python-dict-style single-quoted keys/values to valid JSON
    double quotes -- a common malformation when the model echoes back
    something closer to a Python literal than JSON. Only rewrites
    single quotes in clearly key/value positions (immediately before a
    colon, or immediately after one) to avoid mangling an apostrophe
    inside otherwise double-quoted prose (e.g. "the student's answer")."""
    text = _SINGLE_QUOTED_KEY_RE.sub(lambda m: f'"{m.group(1)}":', text)
    text = _SINGLE_QUOTED_VAL_RE.sub(lambda m: f': "{m.group(1)}"', text)
    return text


_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def repair_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


# Two closing quotes/values sitting directly next to the start of the next
# key with nothing between them ("...value" "next_key": ...) -- missing
# comma between sibling fields, a slightly broader net than the
# error-position-driven repair in qwen_adapter (this one is a static regex
# so it can run as an independent, adapter-agnostic stage).
_MISSING_COMMA_BETWEEN_STRINGS_RE = re.compile(r'"\s*\n?\s*"(?=(?:[A-Za-z_][A-Za-z0-9_ ]*"\s*:))')
_MISSING_COMMA_AFTER_SCALAR_RE = re.compile(
    r'(?P<val>-?\d+(?:\.\d+)?|true|false|null)\s*\n\s*(?="[A-Za-z_])')
_MISSING_COMMA_AFTER_BRACKET_RE = re.compile(r'([}\]])\s*\n\s*(?="[A-Za-z_][A-Za-z0-9_ ]*"\s*:)')


def repair_missing_commas_heuristic(text: str) -> str:
    """Static-pattern (not error-position-driven) missing-comma repair,
    covering the shapes qwen_adapter's error-position repair can miss when
    several other malformations are present at once and json.loads never
    gets far enough to report "Expecting ',' delimiter" at a useful
    position. Only inserts a comma at junctions that are unambiguous:
    string-then-string, scalar-then-newline-then-key, closer-then-key."""
    text = _MISSING_COMMA_BETWEEN_STRINGS_RE.sub('",\n"', text)
    text = _MISSING_COMMA_AFTER_SCALAR_RE.sub(lambda m: f"{m.group('val')},\n", text)
    text = _MISSING_COMMA_AFTER_BRACKET_RE.sub(r"\1,\n", text)
    return text


# "key" "value"  (missing colon) -- but not "key": "value" (already correct)
# and not two independently-quoted array items ("a" "b" inside a list),
# which this pattern deliberately does not try to disambiguate from --
# only fires when it looks like a key (short, identifier-ish) immediately
# followed by a value-shaped token with no colon at all.
_MISSING_COLON_RE = re.compile(
    r'"(?P<key>[A-Za-z_][A-Za-z0-9_ ]{0,60})"\s+(?="|-?\d|true\b|false\b|null\b|\{|\[)')


def repair_missing_colons(text: str) -> str:
    """Inserts a colon between what looks like a bare object key and the
    value that immediately follows it with no separator at all. Applied
    only to text that still fails to parse, and only as one candidate
    repair among several -- see repair_and_parse's ordering."""
    def _fix(m: "re.Match") -> str:
        return f'"{m.group("key")}":'
    return _MISSING_COLON_RE.sub(_fix, text)


def repair_missing_comma(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """Error-position-driven missing-comma repair (same technique as
    qwen_adapter._repair_missing_comma): json.loads is precise about this
    failure ("Expecting ',' delimiter" at an exact index), so the safest
    fix is inserting exactly one comma there and nothing else."""
    if error.msg != "Expecting ',' delimiter":
        return None
    pos = error.pos
    return text[:pos] + "," + text[pos:]


def repair_extra_data(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """General 'Extra data' repair: keeps the first value that parses
    cleanly on its own and discards whatever trailing content follows it
    (duplicate answer, trailing prose, a second unrelated object -- in all
    these cases the first parseable value is the one worth keeping)."""
    if error.msg != "Extra data":
        return None
    candidate = text[:error.pos]
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return candidate


# ===========================================================================
# Stage 3 — LaTeX / math / chemistry / physics notation repairs
# ===========================================================================
# Any backslash NOT already forming a valid JSON escape (\" \\ \/ \b \f \n
# \r \t \uXXXX -- and \uXXXX only counts when 4 real hex digits follow) is
# almost certainly the start of a LaTeX command (\frac, \sqrt, \text,
# \left, \right, \sum, \int, \alpha, \rightarrow, \Delta, \times, \cdot,
# \pm, \leq, \geq, \neq, ...) or a chemistry/physics shorthand escape
# (\ce, \isotope, ...). Doubling it is meaning-preserving: the model
# always intends a literal backslash character here, never an actual JSON
# control escape. This is syntax-driven (valid-JSON-escape grammar), not a
# LaTeX command whitelist -- any command not starting with b/f/n/r/t/u
# (\alpha, \times, \substack, \boxed, \overrightarrow, or any future
# command) is already caught here with no enumeration required.
_INVALID_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})')

# COLLISION NOTE: _INVALID_ESCAPE_RE above treats \b \f \n \r \t \uXXXX as
# already-valid JSON escapes and leaves them alone -- correct for a
# genuine escape, but several extremely common LaTeX commands *start*
# with exactly those letters (\frac, \forall, \nabla, \neq, \notin,
# \rightarrow, \right, \rho, \tan, \theta, \times, \to, \underline,
# \uparrow, \bar, \beta, \binom, \boxed, \substack -- and any future
# command spelled the same way). Left alone, json.loads wouldn't even
# raise here -- it would "succeed" by silently consuming e.g. "\f" as a
# form-feed control character and leaving "rac{...}" behind as corrupted
# literal text. These have to be double-escaped FIRST, before the generic
# pass above, using a lookahead so only the colliding backslash itself is
# touched.
#
# WHY THIS ISN'T (AND CAN'T FULLY BE) A PURE SYNTAX RULE: a first attempt
# at this pattern used "backslash + [bfnrt] + another letter, no
# enumeration at all". That over-fired on completely ordinary, valid
# content: genuine escaped text such as "line one\nline two" has \n
# followed immediately by more letters ("line") with no separator -- a
# real, common shape, not an edge case. Distinguishing "\n" (a newline,
# followed by prose) from "\nabla" (a command) is not decidable from
# local syntax alone; it requires recognizing the word as a command.
# Rather than pretend otherwise, this is split into two parts:
#
#   1. GENERIC / SYNTAX-BASED (no enumeration): a backslash followed by
#      one of b/f/n/r/t/u and then more letters and then an IMMEDIATE
#      `{` is a group-taking command -- \frac{, \binom{, \boxed{,
#      \underset{, \underline{, or any future b/f/n/r/t/u-prefixed
#      command with an argument group. Genuine prose escapes (\n, \t, a
#      real \uXXXX) are essentially never followed immediately by a
#      literal `{`, so this generalizes to any current or future
#      group-taking command with no enumeration and no false positives
#      on ordinary escaped text.
#   2. A small, explicit, EXPLICITLY NOT EXHAUSTIVE set of well-
#      established operators/symbols that also collide but are
#      conventionally used WITHOUT a following group (\tan x, \to,
#      \theta, \nabla f, ...), so rule 1's brace signal can't catch
#      them. This list exists only because that specific ambiguity has
#      no syntax-only answer -- it is not relied on for brace-balancing
#      (repair_malformed_latex_groups below is fully generic) and does
#      not need to be exhaustive for the group-taking case (1) to keep
#      working on any unknown/future command.
_COLLIDING_BRACELESS_OPERATORS = (
    "rightarrow", "notin", "nabla", "theta", "times", "right",
    "forall", "neq", "rho", "tan", "to", "beta", "tau", "bmod",
)
_braceless_alt = "|".join(
    sorted(_COLLIDING_BRACELESS_OPERATORS, key=len, reverse=True))

# IDEMPOTENCY GUARD: `(?<!\\)` -- once a colliding backslash has been
# doubled (by this same pass, or an earlier one, e.g. the unconditional
# pre-pass in repair_and_parse followed by this function running again at
# Stage 5 when a *different* part of the text still fails to parse), the
# second backslash of that now-correct pair must never be re-matched as a
# "new" collision -- doing so would triple-escape it and corrupt the
# content. The lookbehind restricts matches to a backslash that is not
# itself preceded by another backslash, so an already-fixed `\\beta` is
# left untouched on every subsequent pass.
_COLLIDING_LATEX_RE = re.compile(
    r"(?<!\\)\\(?="
    r"[bfnrt][A-Za-z]*\{"                  # \frac{, \binom{, \boxed{, ... (any command, any length)
    r"|u(?![0-9a-fA-F]{4})[A-Za-z]*\{"     # \underset{, \underline{, ... (not a real \uXXXX escape)
    r"|(?:" + _braceless_alt + r")\b"      # small explicit set of common brace-less operators
    r")"
)


def repair_latex_backslashes(text: str) -> str:
    """Escapes bare backslashes that introduce a LaTeX command (\\frac,
    \\sqrt, \\text, \\left, \\right, \\sum, \\int, arrows, greek letters,
    operators, \\binom, \\boxed, \\substack, \\overrightarrow, or any
    other/future command) or chemistry notation (\\ce{...}) so json.loads
    no longer sees an 'Invalid \\escape' -- or worse, silently swallows a
    colliding one (\\frac, \\right, \\neq, ...) as its own valid-but-wrong
    control-character escape. Detection of GROUP-TAKING commands (the
    \\frac{, \\binom{, \\boxed{ shape) is fully generic/syntax-based with
    no command-name enumeration, so an unrecognized or brand-new command
    is handled exactly like a well-known one; a small, explicitly
    non-exhaustive set of common BRACE-LESS operators (\\tan, \\to,
    \\theta, ...) is also recognized, since that narrower ambiguity
    (a genuine "\\n" escape vs. "\\nabla") has no syntax-only answer --
    see _COLLIDING_LATEX_RE's comment for why. Every backslash the model
    emits in this context is intended literally, so doubling only these
    ones (already-valid JSON escapes like a genuine \\n line break are
    left untouched) never changes meaning."""
    text = _COLLIDING_LATEX_RE.sub(r"\\\\", text)
    return _INVALID_ESCAPE_RE.sub(r"\\\\", text)


def _brace_balance_within(s: str, start: int) -> int:
    """Returns the net {/} balance of s starting at index `start` up to
    (and including) the point where it first returns to zero, or the net
    balance at end-of-string if it never does. Helper for
    repair_malformed_latex_groups below."""
    depth = 0
    for ch in s[start:]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth


# A LaTeX command token: one or two leading backslashes (a doubled
# backslash is valid JSON-escaped-backslash-then-command, seen after
# earlier repair stages) followed by one or more letters -- \frac, \sqrt,
# \binom, \boxed, \substack, \overrightarrow, \underset, or any other
# current or future command. GENERIC / SYNTAX-BASED ON PURPOSE: this is
# not a whitelist of named commands (the previous implementation's
# `(frac|sqrt|sum|int|...)` enumeration is gone) -- ANY backslash-word
# token is treated as a group-taking command, so an unrecognized or
# brand-new command is balanced exactly like a well-known one. A command
# that happens to take no {...} group at all (\pi, \times, \alpha, ...) is
# harmless here too: the walk below only fires when a `{` immediately
# follows, so a bare command with no group is just passed through as-is.
_LATEX_GROUP_COMMAND_RE = re.compile(r"\\\\?[A-Za-z]+")


def repair_malformed_latex_groups(text: str) -> str:
    """Best-effort balancing of {...} groups belonging to ANY LaTeX
    command (\\frac, \\sqrt, \\text, \\binom, \\boxed, \\substack,
    \\overrightarrow, \\underset, or any other/future command -- matched
    generically by syntax, not by a fixed command-name list) when
    OCR/VLM output truncated or dropped a closing brace mid-command.
    Only ever ADDS closing braces immediately after the offending
    command's content — never removes or rewrites characters — so it
    can't silently change any value that was already well-formed."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = _LATEX_GROUP_COMMAND_RE.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        out.append(m.group(0))
        i = m.end()
        # Walk any number of consecutive {...} groups this command takes
        # (\frac has two, \sqrt/\text/\sum/\int have one each), balancing
        # each individually so an unterminated one doesn't swallow the
        # rest of the surrounding JSON looking for its close.
        while i < n and text[i] == "{":
            depth = 0
            j = i
            while j < n:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                elif text[j] == '"' and depth > 0:
                    # A stray unescaped quote ended the JSON string before
                    # this LaTeX group closed -- stop here rather than
                    # walk past the string boundary.
                    break
                j += 1
            group_text = text[i:j]
            missing = group_text.count("{") - group_text.count("}")
            if missing > 0:
                group_text = group_text + ("}" * missing)
            out.append(group_text)
            i = j
    return "".join(out)


# Common broken/OCR-mangled arrow and math-operator sequences that surface
# as plain (non-backslash) text -- these don't break JSON syntax by
# themselves, but normalizing them keeps semantic content consistent for
# Phase 2 rather than leaving visibly-corrupted math in the Master JSON.
_ARROW_FIXES = [
    (re.compile(r"-{2,}>"), "\u2192"),          # -->  =>  →
    (re.compile(r"={2,}>"), "\u21d2"),          # ==>  =>  ⇒
    (re.compile(r"<-{2,}"), "\u2190"),          # <--  =>  ←
    (re.compile(r"<={2,}"), "\u21d0"),          # <==  =>  ⇐
]
_OPERATOR_FIXES = [
    (re.compile(r"(?<=\d)\s*x\s*(?=\d)"), "\u00d7"),   # "2 x 3" -> "2 × 3" (bare OCR 'x' as multiply)
    (re.compile(r"<="), "\u2264"),
    (re.compile(r">="), "\u2265"),
    (re.compile(r"!="), "\u2260"),
    (re.compile(r"\+-"), "\u00b1"),
]


def normalize_unicode_math_symbols(text: str) -> str:
    """Normalizes common OCR/plain-text renderings of arrows and
    comparison/arithmetic operators to their proper unicode math symbols.
    Purely cosmetic/semantic normalization -- unicode characters are
    always valid inside a JSON string, so this never affects
    parseability; it runs to preserve mathematical meaning/consistency in
    the Master JSON, not to fix a JSON error."""
    for pattern, repl in _ARROW_FIXES:
        text = pattern.sub(repl, text)
    for pattern, repl in _OPERATOR_FIXES:
        text = pattern.sub(repl, text)
    return text


# Superscript/subscript shorthand the OCR layer sometimes emits as bare
# "^2" / "_2" outside of LaTeX math mode. These are already valid JSON
# characters (no escaping issue), so no repair is required for parsing —
# but a stray unescaped caret next to a quote can visually suggest a typo;
# left untouched deliberately (touching it risks altering `sem.get("latex")`
# content Phase 2 depends on byte-for-byte).
_CHEMISTRY_SUBSCRIPT_HINT_RE = re.compile(r"\b([A-Z][a-z]?)(\d)\b")  # e.g. H2O, CO2 (informational only)


def repair_ocr_escape_noise(text: str) -> str:
    """Cleans up a few specific OCR-introduced escape artifacts seen in
    mixed OCR+LaTeX output: a stray backslash directly before a digit or
    whitespace with no letter command after it (OCR occasionally inserts
    a bare '\\' where a broken character recognition produced a lone
    slash), and doubled/tripled backslashes that should be single before
    a recognized LaTeX command name (over-escaping from a previous lossy
    round-trip)."""
    # Collapse 3+ backslashes down to exactly 2 (i.e. one escaped
    # backslash) immediately before ANY LaTeX command word -- over-
    # escaping artifact from repeated cleanup passes upstream. Detected
    # generically by syntax (a run of 3+ backslashes directly followed by
    # letters), not by a fixed command-name list, so an unrecognized or
    # future command is collapsed exactly like a well-known one.
    text = re.sub(r"\\{3,}(?=[A-Za-z])", r"\\\\", text)
    # A backslash immediately followed by whitespace or end-of-string is
    # never a valid LaTeX command nor a valid JSON escape -- almost always
    # OCR noise. Safe to escape (not delete) so we never lose a character
    # the model may have meant as literal.
    text = re.sub(r"\\(?=\s|$)", r"\\\\", text)
    return text


# ===========================================================================
# Stage 4 — truncation recovery
# ===========================================================================
_TRUNCATION_CLOSERS = {"{": "}", "[": "]"}


def repair_truncated_json(text: str) -> Optional[str]:
    """Closes whatever is structurally still open (an in-progress string,
    then any unclosed [ / { in last-opened-first order) when generation
    was cut off mid-answer. Never fabricates field content -- only closes
    open delimiters. Returns None when nothing looks unterminated."""
    in_string = False
    escaped = False
    stack: List[str] = []
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in _TRUNCATION_CLOSERS:
            stack.append(_TRUNCATION_CLOSERS[ch])
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()

    if not in_string and not stack:
        return None

    repaired = text
    if in_string:
        repaired += '"'
    repaired += "".join(reversed(stack))
    return repaired


# ===========================================================================
# Orchestration — validate after EVERY stage, stop at the first success
# ===========================================================================
@dataclass
class RepairResult:
    success: bool
    parsed: Optional[Any] = None
    repaired_text: Optional[str] = None
    stages_applied: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _try_parse(text: str) -> Tuple[bool, Any]:
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, None


def repair_and_parse(raw: str, max_comma_repairs: int = 6) -> RepairResult:
    """The production-grade repair pipeline. Applies one repair at a time,
    from least-invasive/most-certain to most speculative, RE-VALIDATING
    with json.loads after every single stage rather than performing one
    big cleanup pass — so the pipeline always returns via the earliest,
    smallest fix that actually works, and never applies a riskier repair
    once an earlier one already produced valid JSON.

    Never raises. Returns a RepairResult; `success=False` means every
    repair attempt was exhausted and the caller (an adapter's
    generate_json, or a retry loop) should treat this as an ordinary
    "model didn't return usable JSON" outcome.
    """
    stages: List[str] = []

    if raw is None or not str(raw).strip():
        return RepairResult(success=False, error="empty input")

    text = str(raw)

    # Applied unconditionally, before the first parse attempt: a backslash
    # immediately preceding a LaTeX command name that collides with one of
    # JSON's own valid escape letters (\frac, \right, \neq, \nabla, ...)
    # would otherwise let json.loads "succeed" on the very first try while
    # silently corrupting the string content (\f consumed as a form feed,
    # "rac{a}{b}" left behind as literal text) -- see _COLLIDING_LATEX_RE's
    # docstring. This can never fire on genuinely-intended JSON content, so
    # it is always safe to apply before anything else.
    if _COLLIDING_LATEX_RE is not None:
        collision_fixed = _COLLIDING_LATEX_RE.sub(r"\\\\", text)
        if collision_fixed != text:
            stages.append("repair_colliding_latex_escapes")
            text = collision_fixed

    # Also applied unconditionally, before the first parse attempt: a
    # truncated/unbalanced LaTeX {...} group (e.g. "\binom{n}{k" missing
    # its final close) is syntactically ordinary JSON-string content --
    # json.loads has no notion of LaTeX brace semantics, so it can
    # "succeed" on text like this on the very first try, silently leaving
    # the group unbalanced in the parsed value. Waiting for a parse
    # failure (as every other repair below does) would therefore never
    # even attempt this fix in exactly the cases it matters most. Safe to
    # run unconditionally because it only ever APPENDS closing braces --
    # it never removes or rewrites a character, so it cannot turn
    # already-correct content into something different.
    group_fixed = repair_malformed_latex_groups(text)
    if group_fixed != text:
        stages.append("repair_malformed_latex_groups")
        text = group_fixed

    ok, parsed = _try_parse(text)
    if ok:
        return RepairResult(True, parsed, text, stages)

    # Stage 1: strip markdown fences / prose wrapper -----------------------
    candidate = strip_markdown_fences(text)
    if candidate != text:
        stages.append("strip_markdown_fences")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 2: pick the best single JSON object out of prose/duplicates ----
    best = pick_best_json_object(text)
    if best is not None and best != text:
        stages.append("extract_best_json_object")
        ok, parsed = _try_parse(best)
        if ok:
            return RepairResult(True, parsed, best, stages)
        text = best

    deduped = remove_duplicated_json_blocks(text)
    if deduped != text:
        stages.append("remove_duplicated_json_blocks")
        ok, parsed = _try_parse(deduped)
        if ok:
            return RepairResult(True, parsed, deduped, stages)
        text = deduped

    # Stage 3: smart quotes / single quotes ---------------------------------
    for name, fn in (
        ("normalize_smart_quotes", normalize_smart_quotes),
        ("repair_single_quotes", repair_single_quotes),
    ):
        candidate = fn(text)
        if candidate != text:
            stages.append(name)
            ok, parsed = _try_parse(candidate)
            if ok:
                return RepairResult(True, parsed, candidate, stages)
            text = candidate

    # Stage 4: control characters -------------------------------------------
    candidate = repair_control_characters(text)
    if candidate != text:
        stages.append("repair_control_characters")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 5: LaTeX / math / chemistry / OCR-noise repairs ------------------
    for name, fn in (
        ("repair_malformed_latex_groups", repair_malformed_latex_groups),
        ("repair_ocr_escape_noise", repair_ocr_escape_noise),
        ("repair_latex_backslashes", repair_latex_backslashes),
        ("normalize_unicode_math_symbols", normalize_unicode_math_symbols),
    ):
        candidate = fn(text)
        if candidate != text:
            stages.append(name)
            ok, parsed = _try_parse(candidate)
            if ok:
                return RepairResult(True, parsed, candidate, stages)
            text = candidate

    # Stage 6: truncation (must run before generic comma/colon repair --
    # an unterminated string/object otherwise makes downstream regexes
    # guess at positions past the real end of content). -----------------
    candidate = repair_truncated_json(text)
    if candidate is not None:
        stages.append("repair_truncated_json")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        # keep trying further repairs against the truncation-closed text;
        # it's strictly more likely to parse than the still-open original.
        text = candidate

    # Stage 7: missing colons -------------------------------------------
    candidate = repair_missing_colons(text)
    if candidate != text:
        stages.append("repair_missing_colons")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 8: missing commas (heuristic, static-pattern) -----------------
    candidate = repair_missing_commas_heuristic(text)
    if candidate != text:
        stages.append("repair_missing_commas_heuristic")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 9: missing commas (error-position-driven, looped) -------------
    repaired = text
    for _ in range(max_comma_repairs):
        ok, parsed = _try_parse(repaired)
        if ok:
            stages.append("repair_missing_comma_by_position")
            return RepairResult(True, parsed, repaired, stages)
        try:
            json.loads(repaired)
            break
        except json.JSONDecodeError as e:
            fixed = repair_missing_comma(repaired, e)
            if fixed is None:
                break
            repaired = fixed
    text = repaired

    # Stage 10: trailing commas -------------------------------------------
    candidate = repair_trailing_commas(text)
    if candidate != text:
        stages.append("repair_trailing_commas")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 11: brace/bracket balancing (last-resort structural repair) ---
    candidate = balance_braces_and_brackets(text)
    if candidate != text:
        stages.append("balance_braces_and_brackets")
        ok, parsed = _try_parse(candidate)
        if ok:
            return RepairResult(True, parsed, candidate, stages)
        text = candidate

    # Stage 12: extra-data (trailing prose/duplicate answer) --------------
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        candidate = repair_extra_data(text, e)
        if candidate is not None:
            stages.append("repair_extra_data")
            ok, parsed = _try_parse(candidate)
            if ok:
                return RepairResult(True, parsed, candidate, stages)

    # Everything failed.
    try:
        json.loads(text)
        assert False  # unreachable: would have returned above
    except json.JSONDecodeError as e:
        logger.warning("json_repair: exhausted all repair stages (%s). Stages tried: %s",
                        e, stages)
        return RepairResult(success=False, repaired_text=text, stages_applied=stages, error=str(e))