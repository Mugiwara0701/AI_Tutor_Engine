"""
adapters/qwen_adapter.py — the only concrete ModelAdapter implemented at
launch, per scope.

Reuse, not rewrite: singleton model loading, device resolution (GPU/CPU),
and the 4-bit quantization path all stay exactly as they already are in
modules/vlm_inference.py — this file imports and calls that module's
functions directly rather than reimplementing any of it. The only new code
here is (a) the thin ModelAdapter wrapper and (b) Qwen-specific response
cleanup + JSON parsing, which per clarification #2 belongs in the adapter,
not in prompt_manager.
"""
import json
import logging
import re
from typing import List, Optional, Any

from prompt_manager.model_adapter import ModelAdapter, AdapterResponse
from modules import vlm_inference
from modules import json_repair

logger = logging.getLogger("ncert_pipeline.qwen_adapter")

# --- Qwen-specific response cleanup patterns --------------------------------
# Qwen2.5-VL-Instruct, like most instruction-tuned chat models, sometimes
# wraps JSON in a markdown code fence (```json ... ``` or plain ``` ... ```),
# sometimes prefixes it with a sentence of prose ("Sure, here's the JSON:"),
# occasionally leaves a trailing comma before a closing bracket/brace
# (a common "almost valid JSON" quirk from generation), and — because this
# adapter's tasks routinely ask for LaTeX (equation_analysis, table_analysis,
# etc.) — very often emits raw, un-escaped backslashes from LaTeX commands
# (\vec, \sigma, \frac, ...) inside JSON string values. JSON only treats
# \", \\, \/, \b, \f, \n, \r, \t and \uXXXX as valid escapes, so a value
# like "$\vec{v}$" is invalid JSON as written and json.loads raises
# "Invalid \escape". These cleanup steps are specific to how *this* model
# tends to misbehave — a different backend's adapter might need different
# cleanup, which is exactly why this lives here and not in prompt_manager.
_MD_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
# Matches a backslash NOT followed by one of the valid JSON escape chars.
# We escape just that backslash (\v -> \\v) so the following character
# (e.g. the "v" in "\vec") survives as a literal char instead of being
# consumed as part of an invalid escape sequence.
_INVALID_ESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])')

# Raw control characters (0x00-0x1F) that json.loads rejects verbatim
# inside a string literal ("Invalid control character at: ..."). Qwen
# occasionally emits a literal newline/tab inside a JSON string value
# (e.g. when a "semantic_meaning" or "spoken_form" field spans what it
# treats as multiple lines) instead of the escaped \n/\t JSON requires.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")
_CONTROL_CHAR_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _strip_markdown_fences(text: str) -> str:
    return _MD_FENCE_RE.sub("", text).strip()


def _extract_json_block(text: str) -> str:
    """If there's prose around the JSON (e.g. "Here's the result: {...}"),
    grab the outermost {...} block rather than trying to parse the whole
    string."""
    m = _JSON_BLOCK_RE.search(text)
    return m.group(0) if m else text


def _repair_trailing_commas(text: str) -> str:
    """Removes a comma immediately before a closing } or ] — a very common,
    safe-to-fix malformation: never changes meaning, only removes a syntax error."""
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _repair_control_characters(text: str) -> str:
    """Escapes raw control characters (literal newline/tab/etc.) that
    appear INSIDE a JSON string literal. json.loads refuses these outright
    ("Invalid control character at: ..."), but a raw '\\n' the model
    generated mid-string almost always just means "new line of the
    explanation I'm writing", not an actual structural break -- so
    escaping it in place (rather than deleting it) is meaning-preserving,
    same principle as _repair_invalid_escapes above.

    Walks the text one character at a time, tracking whether we're
    currently inside a string literal (toggled on unescaped `"`, same as
    a minimal JSON tokenizer would), and only rewrites control characters
    found there -- control characters outside any string (typically just
    the newlines used to pretty-print the JSON itself) are left alone."""
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
            if _CONTROL_CHAR_RE.match(ch):
                # Any other raw control byte (rare) carries no meaningful
                # content worth preserving -- drop it rather than risk
                # emitting another invalid escape.
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


# Matching pairs used by _repair_truncated_json below, in "closes-first"
# order (a string, if still open, must be closed before any bracket).
_TRUNCATION_CLOSERS = {"{": "}", "[": "]"}


def _repair_truncated_json(text: str) -> Optional[str]:
    """Best-effort repair for JSON that was cut off mid-generation (e.g. the
    model hit max_new_tokens before finishing its answer) -- one of the
    malformation classes the earlier repair steps above don't attempt,
    since they all assume the text is otherwise complete. Rather than
    guess at missing field content, this only closes what's structurally
    still open: an unterminated string, then any unclosed [ / { in
    last-opened-first order, then retries json.loads. If json.loads still
    fails after that, this was not (purely) a truncation problem and the
    caller falls through to reporting failure as before -- this never
    fabricates field values, only closes open delimiters."""
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
        return None  # nothing looked unterminated -- not a truncation case

    repaired = text
    if in_string:
        repaired += '"'
    repaired += "".join(reversed(stack))
    return repaired


def _repair_invalid_escapes(text: str) -> str:
    """Escapes backslashes that aren't part of a valid JSON escape sequence.

    Qwen frequently returns LaTeX (e.g. "$\\vec{v}_2=2$", "$\\sigma_3=3$")
    inside JSON string values without doubling the backslash, which is what
    valid JSON requires. json.loads then fails with "Invalid \\escape"
    because e.g. \\v and \\s aren't recognized JSON escapes.

    This is a safe, meaning-preserving repair: every backslash in the
    output is intended by the model to be a literal backslash (LaTeX
    syntax), never an actual JSON control escape like \\n or \\t — Qwen
    is not generating JSON control characters here, it's generating LaTeX.
    So doubling only the *invalid* backslashes (leaving already-valid
    escapes like \\n or \\" untouched) recovers the model's intended
    string without altering any real escape sequence."""
    return _INVALID_ESCAPE_RE.sub(r"\\\\", text)


# Signature of the stray-glued-brace malformation: a closing string quote
# with a `}` glued directly onto it (no comma, no newline -- the tell,
# since a real field boundary always has a comma or is the object's last
# field followed by whitespace-then-brace on its own line), where that
# glued brace is itself immediately followed by another `}` and then a
# comma. The trailing comma is what makes this identifiable and safe: it
# means the model still intended more sibling keys to follow, so the brace
# that comma follows closed something one level higher than intended --
# i.e. the *first* (glued) brace was the stray one, not the second. A
# genuinely-final, correctly-nested double-close (e.g. a single-field
# top-level object's last value) is never followed by a comma, so this
# pattern does not match ordinary valid JSON in this pipeline's (always
# flat, never-array) output shape.
_STRAY_GLUED_BRACE_RE = re.compile(r'"\}(?=\s*\},)')

# Cap on how many missing-comma fixes we'll apply to a single response.
# Qwen occasionally drops more than one delimiter in a long, many-field
# object (topic_semantics has 8 top-level keys), so a single fix-and-retry
# isn't always enough. A hard cap keeps this from ever looping unboundedly
# on a response that is malformed in some other, unrelated way.
_MAX_MISSING_COMMA_REPAIRS = 5


def _repair_missing_comma(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """Repairs the single most common Qwen malformation seen in production:
    two sibling fields with no comma between them, e.g.
        "visual_summary": {...}
        "concepts": [...]
    json.loads is precise about this failure mode — error.msg is exactly
    "Expecting ',' delimiter" and error.pos is exactly the character index
    where it found the start of the next token instead of the comma it
    needed. That means the fix doesn't need a regex guess at all: insert a
    single comma at error.pos and nothing else in the string changes, so
    this can never alter any value the model actually returned.

    Only fires for this specific error message; any other JSONDecodeError
    falls through unchanged so the caller's other repairs still run."""
    if error.msg != "Expecting ',' delimiter":
        return None
    pos = error.pos
    return text[:pos] + "," + text[pos:]


def _repair_stray_closing_brace(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """Repairs one observed Qwen malformation: an extra `}` glued directly
    onto the end of a nested field's closing string quote, with no comma —
    e.g. `"evidence_basis": "..."}\\n  },` where a normal, correctly-nested
    object would just have `"evidence_basis": "..."\\n  },`. json.loads
    actually parses *through* both the glued brace and the next real one as
    a syntactically complete (but wrong) top-level object, and reports
    everything genuinely meant to follow (further keys, the real remaining
    closing braces) as "Extra data" — it does not point at the stray brace
    itself, so locating it needs the pattern match in
    _STRAY_GLUED_BRACE_RE, not the reported error position.

    Only invoked when parsing has already failed with that specific error,
    and only removes one brace character it can positively identify via the
    pattern above — it never touches any string's content, so it can't
    silently change a value the model actually returned. Returns the
    repaired text, or None if the pattern isn't found (so the caller falls
    through to reporting failure exactly as before)."""
    if error.msg != "Extra data":
        return None
    if not _STRAY_GLUED_BRACE_RE.search(text):
        return None
    return _STRAY_GLUED_BRACE_RE.sub('"', text, count=1)


def _repair_trailing_extra_data(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """Repairs one specific "Extra data" cause: the model produced a
    complete, correctly-formed JSON value and then repeated it a second
    time (a known VLM repetition failure mode) -- e.g. it answers, then
    keeps generating and answers the same question again verbatim. This is
    distinct from _repair_stray_closing_brace above (a *wrong*, one-level-
    too-shallow object caused by a glued extra brace) and, importantly,
    from the case of two genuinely *different* JSON objects concatenated
    together, which must still be reported as a failure rather than have
    this repair arbitrarily keep the first one and discard the second --
    see test_clean_and_parse_still_fails_cleanly_when_no_repair_applies.

    So this only fires when the leftover content ("Extra data") parses out
    to something equal to the first value -- true duplication, not merely
    "also happens to be valid JSON". json.JSONDecodeError's `pos` for this
    error is exactly the index where the leftover starts, so text[:pos] is
    the first complete value and text[pos:] is everything after it."""
    if error.msg != "Extra data":
        return None
    candidate = text[:error.pos]
    try:
        first_value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    remainder = text[error.pos:].strip()
    if not remainder:
        return None
    try:
        remainder_value = json.loads(remainder)
    except json.JSONDecodeError:
        return None
    if remainder_value != first_value:
        return None
    return candidate


def clean_and_parse_qwen_output(raw: str) -> AdapterResponse:
    """Qwen-specific cleanup pipeline -> defensive JSON parse -> AdapterResponse.
    Never raises: any failure comes back as success=False with error_message
    set, since 'the model didn't return clean JSON' is an ordinary, expected
    outcome that prompt_manager's retry logic handles — not an exception."""
    if not raw or not raw.strip():
        return AdapterResponse(success=False, raw_output=raw or "", cleaned_output="",
                                parsed_output=None, error_message="empty model output")

    cleaned = _strip_markdown_fences(raw)
    cleaned = _extract_json_block(cleaned)

    # PART 1 addition: several very common LaTeX commands (\frac, \forall,
    # \nabla, \neq, \notin, \right, \rightarrow, \rho, \tan, \theta, \times,
    # \to, \underline, \uparrow, \bar, \beta, \binom, ...) start with a
    # letter that JSON's own escape grammar also recognizes (\f, \n, \r,
    # \t, \b, \u...). Left alone, json.loads would not raise at all here —
    # it would "succeed" by silently consuming e.g. "\f" as a form feed and
    # leaving "rac{...}" behind as corrupted literal text. This has to be
    # fixed BEFORE the first parse attempt (not only as a failure-path
    # repair), since a corrupting "success" never reaches any of the
    # exception-driven repairs below. Safe unconditionally: this pattern
    # never legitimately means an actual control character in this
    # pipeline's math/equation/table extraction output.
    cleaned = json_repair.repair_latex_backslashes(cleaned) \
        if json_repair._COLLIDING_LATEX_RE is not None and json_repair._COLLIDING_LATEX_RE.search(cleaned) \
        else cleaned

    # First attempt: parse as-is.
    try:
        parsed = json.loads(cleaned)
        return AdapterResponse(success=True, raw_output=raw, cleaned_output=cleaned, parsed_output=parsed)
    except json.JSONDecodeError:
        pass

    # Second attempt (ISSUE 2 addition): raw control characters (literal
    # newline/tab/...) inside a string value -- "Invalid control character
    # at: ..." -- repaired before any of the other targeted repairs below,
    # since a stray control byte inside a string can otherwise throw off
    # the character-position-based repairs (missing comma, stray brace)
    # that follow.
    cleaned = _repair_control_characters(cleaned)
    try:
        parsed = json.loads(cleaned)
        return AdapterResponse(success=True, raw_output=raw, cleaned_output=cleaned, parsed_output=parsed)
    except json.JSONDecodeError:
        pass

    # Third attempt (ISSUE 2 addition): truncated JSON -- an unterminated
    # string and/or unclosed object/array from the response being cut off
    # mid-generation. Tried here, BEFORE the missing-comma repair below,
    # because Python's json.loads reports an incomplete array/object's
    # missing closing bracket as "Expecting ',' delimiter" (the same
    # message a genuinely-complete-but-comma-dropping response produces),
    # which would otherwise send this down the wrong repair path and
    # insert a comma into a string that was never going to be valid JSON
    # no matter how many commas are added.
    truncation_repaired = _repair_truncated_json(cleaned)
    if truncation_repaired is not None:
        try:
            parsed = json.loads(truncation_repaired)
            return AdapterResponse(success=True, raw_output=raw, cleaned_output=truncation_repaired,
                                    parsed_output=parsed)
        except json.JSONDecodeError:
            pass  # not (purely) a truncation problem -- fall through unchanged

    # Third attempt: repair missing-comma-between-fields, the single most
    # common malformation observed in production logs ("Expecting ','
    # delimiter"). Looped (bounded by _MAX_MISSING_COMMA_REPAIRS) because a
    # long, many-field object (e.g. topic_semantics' 8 top-level keys) can
    # drop more than one delimiter in a single response. Cheap: no second
    # model call, just a string insert at the exact position json.loads
    # already told us it expected a comma.
    repaired = cleaned
    for _ in range(_MAX_MISSING_COMMA_REPAIRS):
        try:
            parsed = json.loads(repaired)
            return AdapterResponse(success=True, raw_output=raw, cleaned_output=repaired, parsed_output=parsed)
        except json.JSONDecodeError as e:
            fixed = _repair_missing_comma(repaired, e)
            if fixed is None:
                break
            repaired = fixed
    cleaned = repaired

    # Third attempt: repair the other common, safe-to-fix issue (trailing
    # commas before a closing brace/bracket) and retry. This is a minor,
    # meaning-preserving repair only — we do not attempt speculative fixes
    # (e.g. guessing missing quotes) that could silently change the model's
    # actual answer.
    repaired = _repair_trailing_commas(cleaned)
    try:
        parsed = json.loads(repaired)
        return AdapterResponse(success=True, raw_output=raw, cleaned_output=repaired, parsed_output=parsed)
    except json.JSONDecodeError:
        pass

    # Fourth attempt: repair un-escaped backslashes left over from LaTeX
    # content (\vec, \sigma, \frac, ...) — the other common, safe-to-fix
    # issue for this adapter's math/equation/table tasks — on top of the
    # trailing-comma repair, and retry.
    repaired = _repair_invalid_escapes(repaired)
    try:
        parsed = json.loads(repaired)
        return AdapterResponse(success=True, raw_output=raw, cleaned_output=repaired, parsed_output=parsed)
    except json.JSONDecodeError as e:
        # Fifth attempt: the one remaining common malformation — a stray
        # extra `}` closing a nested object one field too early (see
        # _repair_stray_closing_brace's docstring). Only fires on this
        # specific "Extra data" error shape; anything else falls through to
        # reporting failure exactly as before.
        stray_brace_repaired = _repair_stray_closing_brace(repaired, e)
        if stray_brace_repaired is not None:
            try:
                parsed = json.loads(stray_brace_repaired)
                return AdapterResponse(success=True, raw_output=raw, cleaned_output=stray_brace_repaired,
                                        parsed_output=parsed)
            except json.JSONDecodeError:
                pass

        # Sixth attempt: general "Extra data" repair -- the model produced a
        # complete, valid JSON value and then kept generating (most often a
        # repeated copy of the same answer). Distinct from the stray-brace
        # case just above: here the first-parsed value is already correct,
        # just followed by noise, so truncating to it is safe. See
        # _repair_trailing_extra_data's docstring for why this must run
        # after, not instead of, the stray-brace repair.
        extra_data_repaired = _repair_trailing_extra_data(repaired, e)
        if extra_data_repaired is not None:
            try:
                parsed = json.loads(extra_data_repaired)
                return AdapterResponse(success=True, raw_output=raw, cleaned_output=extra_data_repaired,
                                        parsed_output=parsed)
            except json.JSONDecodeError:
                pass

        # Seventh attempt (PART 1 addition — production-grade repair
        # layer): the broader, model-agnostic repair stages in
        # modules/json_repair.py -- LaTeX (\frac/\sqrt/\text/\left/\right/
        # \sum/\int/arrows/greek/operator) backslash + group repair,
        # chemistry/physics/OCR escape-noise cleanup, smart/single quote
        # normalization, missing-colon repair, a broader static-pattern
        # missing-comma heuristic, and brace/bracket balancing. These are
        # deliberately applied one at a time with a re-parse after each
        # (never one big pass), and deliberately do NOT re-run the
        # multi-object "pick the best candidate" / duplicate-collapsing
        # step already attempted above via _repair_stray_closing_brace /
        # _repair_trailing_extra_data -- so a genuinely ambiguous case
        # (two different, both-valid, concatenated JSON objects) still
        # correctly falls through to reporting failure rather than this
        # stage arbitrarily guessing one of them.
        structural_repaired = repaired
        for repair_fn in (
            json_repair.repair_malformed_latex_groups,
            json_repair.repair_ocr_escape_noise,
            json_repair.repair_latex_backslashes,
            json_repair.normalize_smart_quotes,
            json_repair.repair_single_quotes,
            json_repair.repair_missing_colons,
            json_repair.repair_missing_commas_heuristic,
            json_repair.repair_trailing_commas,
            json_repair.balance_braces_and_brackets,
        ):
            candidate = repair_fn(structural_repaired)
            if candidate == structural_repaired:
                continue
            structural_repaired = candidate
            try:
                parsed = json.loads(structural_repaired)
                return AdapterResponse(success=True, raw_output=raw, cleaned_output=structural_repaired,
                                        parsed_output=parsed)
            except json.JSONDecodeError:
                continue

        # Truncation can still be the culprit even after the repairs above
        # (e.g. LaTeX-escaping revealed an otherwise-masked unterminated
        # string). One more truncation-close attempt on the
        # furthest-repaired text before giving up.
        truncation_final = json_repair.repair_truncated_json(structural_repaired)
        if truncation_final is not None:
            try:
                parsed = json.loads(truncation_final)
                return AdapterResponse(success=True, raw_output=raw, cleaned_output=truncation_final,
                                        parsed_output=parsed)
            except json.JSONDecodeError:
                pass

        logger.warning("Qwen output was not valid JSON even after cleanup. Error: %s. Cleaned (truncated): %.300s",
                        e, cleaned)
        return AdapterResponse(success=False, raw_output=raw, cleaned_output=cleaned, parsed_output=None,
                                error_message=f"invalid JSON after cleanup: {e}")


class QwenAdapter(ModelAdapter):
    """Concrete adapter for Qwen2.5-VL-3B-Instruct. Holds no model state of
    its own — model_adapter.get_model()'s module-level singleton in
    vlm_inference.py is the actual owner of the loaded weights, exactly as
    before this refactor. This class is a thin conformance wrapper."""

    adapter_id = "qwen2.5-vl-3b-instruct"

    def __init__(self, max_new_tokens: Optional[int] = None):
        self._default_max_new_tokens = max_new_tokens
        self._last_input_tokens: Optional[int] = None
        self._last_output_tokens: Optional[int] = None

    def generate(self, prompt: str, images: Optional[List[Any]] = None,
                 max_new_tokens: Optional[int] = None) -> str:
        """Delegates straight to the existing vlm_inference.generate() —
        singleton loading, device resolution, and quantization path are
        entirely unchanged from before this refactor."""
        return vlm_inference.generate(
            prompt, images=images, max_new_tokens=max_new_tokens or self._default_max_new_tokens)

    def generate_json(self, prompt: str, images: Optional[List[Any]] = None,
                       max_new_tokens: Optional[int] = None) -> AdapterResponse:
        try:
            raw = self.generate(prompt, images=images, max_new_tokens=max_new_tokens)
        except Exception as e:
            # Infrastructure failure (OOM, model not loaded, CUDA error, ...) —
            # prompt_manager distinguishes this from an ordinary bad-JSON
            # response by catching it separately at the call site if desired;
            # here we still report it as a structured (not raised) failure so
            # one bad chapter/page doesn't crash the whole batch run.
            logger.exception("Qwen generate() call failed: %s", e)
            return AdapterResponse(success=False, raw_output="", cleaned_output="",
                                    parsed_output=None, error_message=f"inference error: {e}")
        return clean_and_parse_qwen_output(raw)

    def token_counts(self) -> Optional[dict]:
        """Qwen2.5-VL via transformers doesn't surface token counts through
        the existing vlm_inference.generate() call today (it returns decoded
        text only) — returning None is the documented 'not available'
        signal, not an error. Wiring real counts through would mean changing
        vlm_inference.generate()'s return shape, which is out of scope for
        this step (reuse existing code, don't rewrite it)."""
        return None