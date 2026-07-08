"""
context_builder.py — the only thing that turns a TaskContext payload into
final prompt text. No extraction module builds a prompt string itself; they
hand over structured fields and this module does the substitution according
to the template's declared `{{ variable }}` slots.

Deliberately NOT using Jinja2 here: the templates only need flat variable
substitution (no loops/conditionals), so a small regex-based substitutor
avoids adding a templating-engine dependency for something this simple —
consistent with "prefer the simplest implementation."
"""
import re
from typing import Dict, Any, List

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# ---------------------------------------------------------------------------
# Global JSON/LaTeX-safety suffix (LATEX AND JSON ROBUSTNESS hardening pass).
#
# Root cause of the recurring "Invalid \escape" / "Extra data" / broken
# multiline-equation JSON failures: every one of the ~15 prompt .txt files
# separately tried to explain "respond with strict JSON" in its own words,
# and none of them told the model explicitly how to emit a LaTeX backslash
# (\frac, \text, \rightarrow, \Lambda, ...) inside a JSON string, so the
# model would emit raw single backslashes that json.loads rejects outright.
# modules/json_repair.py's LaTeX-repair stage was doing the real work of
# catching this AFTER the fact on every single call, which the task spec
# explicitly says should be "a safety net, not the primary solution."
#
# Fixing this per-template would mean copy-pasting (and inevitably
# drifting) the same instructions into every prompt file -- a Single Owner
# Principle violation. Instead this is appended ONCE, by prompt_manager.run(),
# to every rendered prompt regardless of task, so the instruction has
# exactly one place to live. json_repair.py's LaTeX stage remains unchanged
# as the safety net for whatever the model still misses.
# ---------------------------------------------------------------------------
JSON_SAFETY_SUFFIX = """

STRICT JSON OUTPUT RULES (apply to your entire response):
- Output ONE valid JSON object and nothing else: no markdown code fences,
  no prose before or after the braces.
- Every backslash inside a JSON string must be a valid JSON escape. A
  LaTeX command such as \\frac, \\text, \\rightarrow, \\left, \\right,
  \\Lambda, or a Greek-letter command MUST be written with the backslash
  doubled inside the JSON string, e.g. write \\\\frac{a}{b}, not \\frac{a}{b}.
  A single backslash followed by a letter that is not one of the JSON
  escapes (", \\\\, /, b, f, n, r, t, u) is invalid JSON and will be rejected.
- Write multiline equations as ONE JSON string with literal \\n for any
  line break inside it -- never an unescaped real newline inside a string.
- Do not end any array or object with a trailing comma.
- Do not emit more than one JSON object; do not repeat or duplicate it.
"""


class TemplateRenderError(Exception):
    pass


def find_template_vars(template_text: str) -> List[str]:
    """All `{{ var }}` slots a template actually references."""
    return sorted(set(_VAR_RE.findall(template_text)))


def render(template_text: str, context: Dict[str, Any]) -> str:
    """Substitutes every `{{ var }}` slot found in the template. Raises if
    the template references a variable that isn't present in `context` —
    a silently-blank prompt section is worse than a loud failure here."""
    missing = [v for v in find_template_vars(template_text) if v not in context]
    if missing:
        raise TemplateRenderError(
            f"Template references variable(s) {missing} not present in the supplied context.")

    def _sub(match: "re.Match") -> str:
        var = match.group(1)
        value = context[var]
        return _stringify(value)

    return _VAR_RE.sub(_sub, template_text) + JSON_SAFETY_SUFFIX


def _stringify(value: Any) -> str:
    """Lists/dicts render as a plain readable list rather than raw Python
    repr, since these end up inside a natural-language prompt."""
    if isinstance(value, (list, tuple)):
        if not value:
            return "(none)"
        return "; ".join(str(v) for v in value)
    if value is None:
        return "(none)"
    return str(value)
