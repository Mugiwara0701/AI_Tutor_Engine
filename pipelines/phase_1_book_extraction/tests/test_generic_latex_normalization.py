"""
tests/test_generic_latex_normalization.py — regression tests for the
Phase 1 Stabilization Sprint (final refinement, Finding 2): replacing
modules/json_repair.py's fixed LaTeX command whitelist with a generic,
syntax-based repair that requires no command-name enumeration.

ROOT CAUSE COVERED: the independent audit found that
repair_malformed_latex_groups() only recognized a fixed whitelist of
~13 command names (frac, sqrt, sum, int, prod, lim, text, mathrm,
mathbf, overline, underline, vec, hat, bar), and the collision-escaping
logic in repair_latex_backslashes()/_COLLIDING_LATEX_RE was driven by a
KNOWN_LATEX_COMMANDS frozenset of ~70 named commands. An NCERT book using
any command outside those lists (\\binom, \\boxed, \\substack, \\overset,
\\underset, \\overrightarrow, or any future command) with a truncated
brace or a JSON-escape-colliding first letter would not be repaired.

This file verifies the whitelist is gone and repair now works purely off
JSON-escape grammar (for collision detection) and brace-balance syntax
(for group repair) -- so it generalizes to commands never seen before,
without needing another patch when the next NCERT book introduces one.
"""
from __future__ import annotations

import pytest

import modules.json_repair as json_repair


# Commands the OLD whitelist-based implementation did NOT recognize.
UNKNOWN_TO_OLD_WHITELIST = [
    "binom", "boxed", "substack", "overset", "underset", "overrightarrow",
    "widehat", "widetilde", "dbinom", "tbinom", "xrightarrow",
]


def _wrap(latex_body: str) -> str:
    """Builds a minimal raw JSON string the way a VLM would actually emit
    it: one literal backslash before the command, embedded in a JSON
    string value."""
    return '{"eq": "' + latex_body + '"}'


class TestNoWhitelistRemains:
    def test_known_latex_commands_constant_removed(self):
        assert not hasattr(json_repair, "KNOWN_LATEX_COMMANDS")

    def test_group_command_regex_is_generic_not_enumerated(self):
        # The pattern source must not spell out specific command names --
        # it should be a generic "backslash + letters" token matcher.
        pattern_source = json_repair._LATEX_GROUP_COMMAND_RE.pattern
        assert "frac" not in pattern_source
        assert "sqrt" not in pattern_source


class TestUnknownCommandsAreRepairedGenerically:
    @pytest.mark.parametrize("command", UNKNOWN_TO_OLD_WHITELIST)
    def test_unbalanced_group_closed_for_unknown_command(self, command):
        raw = _wrap(f"\\{command}{{a}}{{b")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed["eq"].endswith("}")

    def test_binom_missing_close_brace(self):
        raw = _wrap(r"\binom{n}{k")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\binom{n}{k}"}

    def test_boxed_missing_close_brace(self):
        raw = _wrap(r"\boxed{x = 5")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\boxed{x = 5}"}

    def test_overrightarrow_missing_close_brace(self):
        raw = _wrap(r"\overrightarrow{AB")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\overrightarrow{AB}"}

    def test_substack_two_groups_balanced_independently(self):
        raw = _wrap(r"\substack{a=1 \\ b=2")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed["eq"].endswith("}")

    def test_completely_novel_future_command_name(self):
        # A command that doesn't exist in any known LaTeX package today --
        # simulates "a future command" per the finding's own wording.
        raw = _wrap(r"\zzznewcommand{content")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed["eq"].endswith("}")


class TestCollisionDetectionIsSyntaxBased:
    """A backslash colliding with a JSON single-char escape letter
    (b, f, n, r, t) or an invalid \\u sequence must be fixed regardless of
    which command it introduces -- not just a hardcoded list of ~70
    names."""

    def test_binom_collision_b(self):
        raw = _wrap(r"\binom{n}{k}")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\binom{n}{k}"}

    def test_boxed_collision_b(self):
        raw = _wrap(r"\boxed{5}")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\boxed{5}"}

    def test_underset_collision_u(self):
        raw = _wrap(r"\underset{x}{max}")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\underset{x}{max}"}

    def test_genuine_json_newline_escape_still_works(self):
        # A real, intentional \n followed by non-letter content must NOT
        # be treated as a colliding LaTeX command.
        raw = '{"note": "line one\\nline two"}'
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"note": "line one\nline two"}

    def test_genuine_json_unicode_escape_still_works(self):
        raw = '{"symbol": "\\u03b1"}'
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"symbol": "\u03b1"}

    def test_multiple_colliding_and_noncolliding_commands_in_one_string(self):
        # Regression guard for the idempotency bug found during
        # implementation: repeatedly applying collision-doubling within a
        # single repair pass must never re-touch an already-fixed pair.
        raw = _wrap(r"\alpha + \beta - \gamma")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\alpha + \beta - \gamma"}

    def test_three_colliding_commands_in_sequence(self):
        raw = _wrap(r"\frac{a}{b} \neq \boxed{c}")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"eq": r"\frac{a}{b} \neq \boxed{c}"}


class TestIdempotency:
    @pytest.mark.parametrize("raw", [
        _wrap(r"\binom{n}{k"),
        _wrap(r"\boxed{x"),
        _wrap(r"\alpha + \beta"),
        _wrap(r"\frac{a}{b} \neq \boxed{c}"),
        _wrap(r"\overrightarrow{AB"),
    ])
    def test_repair_latex_backslashes_idempotent_on_already_valid_text(self, raw):
        first = json_repair.repair_and_parse(raw)
        assert first.success is True
        # Re-running the full repair pipeline on the ALREADY-repaired,
        # already-valid JSON text must reproduce the identical result --
        # not re-trigger collision-doubling a second time.
        second = json_repair.repair_and_parse(first.repaired_text)
        assert second.success is True
        assert second.parsed == first.parsed

    def test_repair_malformed_latex_groups_idempotent(self):
        raw = r"\binom{n}{k} \boxed{5} \overrightarrow{AB}"
        once = json_repair.repair_malformed_latex_groups(raw)
        twice = json_repair.repair_malformed_latex_groups(once)
        assert once == twice


class TestOcrEscapeNoiseGenericOverEscapeCollapse:
    def test_over_escaped_unknown_command_collapsed(self):
        raw = r"\\\boxed{5}"
        result = json_repair.repair_ocr_escape_noise(raw)
        assert result == r"\\boxed{5}"

    def test_over_escaped_known_command_collapsed(self):
        raw = r"\\\frac{a}{b}"
        result = json_repair.repair_ocr_escape_noise(raw)
        assert result == r"\\frac{a}{b}"


class TestNestedAndMixedContent:
    def test_nested_braces_in_unknown_command_balanced(self):
        raw = _wrap(r"\overset{\hat{x}}{=}")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True

    def test_mixed_text_and_equation_content(self):
        raw = _wrap(r"The value is \boxed{42} which follows from \binom{5}{2")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed["eq"].endswith("}")

    def test_unicode_math_symbol_preserved_alongside_unknown_command(self):
        raw = _wrap(r"\boxed{x} \u2264 5")
        result = json_repair.repair_and_parse(raw)
        assert result.success is True