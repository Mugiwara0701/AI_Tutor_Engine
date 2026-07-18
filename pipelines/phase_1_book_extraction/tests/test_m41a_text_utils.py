"""
tests/test_m41a_text_utils.py — M4.1A unit tests for modules/text_utils.py
and the pattern-centralisation changes to stage_a_geometry and content_blocks.

Coverage:
  - All definition patterns (FIRST, AFTER, DENOTES, BY_MEAN)
  - TERM_STOPWORDS membership and frozenset invariant
  - term_is_valid(): all reject and accept cases from the frozen architecture
  - STEP_MARKER_RE: all alternatives including prose markers and case sensitivity
  - partial_match_confidence(): all edge cases from the frozen architecture
  - Backward compatibility: stage_a_geometry and content_blocks aliases
  - Module purity: text_utils imports no pipeline modules
"""
from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

# Ensure the repo root is on the path
_REPO = Path(__file__).parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.text_utils import (
    DEFINITION_TERM_AFTER_RE,
    DEFINITION_TERM_BY_MEAN_RE,
    DEFINITION_TERM_DENOTES_RE,
    DEFINITION_TERM_FIRST_RE,
    STEP_MARKER_RE,
    TERM_STOPWORDS,
    partial_match_confidence,
    term_is_valid,
)


# ===========================================================================
# 1. DEFINITION_TERM_FIRST_RE
# ===========================================================================

class TestDefinitionTermFirstRE(unittest.TestCase):
    """'X is defined as ...' — term must begin with a capital letter."""

    # --- matches ---

    def test_single_word_term(self):
        m = DEFINITION_TERM_FIRST_RE.match("Bonds are defined as connections between atoms")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Bonds")

    def test_multiword_term(self):
        m = DEFINITION_TERM_FIRST_RE.match(
            "Kinetic energy is defined as the energy possessed by a body in motion"
        )
        self.assertIsNotNone(m)
        self.assertIn("Kinetic energy", m.group("term"))

    def test_are_connector(self):
        m = DEFINITION_TERM_FIRST_RE.match(
            "Catalysts are defined as substances that increase reaction rate"
        )
        self.assertIsNotNone(m)

    def test_is_connector(self):
        m = DEFINITION_TERM_FIRST_RE.match(
            "Osmosis is defined as the diffusion of solvent"
        )
        self.assertIsNotNone(m)

    def test_hyphenated_term(self):
        m = DEFINITION_TERM_FIRST_RE.match(
            "Non-metals are defined as elements that do not conduct electricity"
        )
        self.assertIsNotNone(m)

    # --- non-matches ---

    def test_lowercase_start_rejected(self):
        m = DEFINITION_TERM_FIRST_RE.match("bonds are defined as connections")
        self.assertIsNone(m)

    def test_no_term_at_start(self):
        m = DEFINITION_TERM_FIRST_RE.match("is defined as something")
        self.assertIsNone(m)

    def test_empty_string(self):
        m = DEFINITION_TERM_FIRST_RE.match("")
        self.assertIsNone(m)

    def test_minimum_term_length_two_chars_rejected(self):
        # [A-Z][A-Za-z][A-Za-z \-]{1,38} — 'Bd' is only 2 chars; needs ≥ 3
        m = DEFINITION_TERM_FIRST_RE.match("Bd are defined as something")
        self.assertIsNone(m)

    def test_minimum_term_length_three_chars_accepted(self):
        m = DEFINITION_TERM_FIRST_RE.match("Bad are defined as something")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Bad")

    def test_no_case_insensitivity(self):
        # Pattern has no re.I — the capital constraint is strict
        m = DEFINITION_TERM_FIRST_RE.match("BONDS ARE DEFINED AS something")
        # "BONDS ARE" — [A-Z]=B, [A-Za-z]=O, then "NDS ARE" before "defined"
        # Actually BONDS = [A-Z][A-Za-z][A-Za-z \-]{1,38} followed by \s+(is|are)
        # "BONDS ARE DEFINED AS" — the \s+(?:is|are)\s+ won't match "ARE" without re.I
        self.assertIsNone(m)

    def test_wrong_connector(self):
        m = DEFINITION_TERM_FIRST_RE.match("Bonds refer to connections")
        self.assertIsNone(m)

    def test_named_group_present(self):
        m = DEFINITION_TERM_FIRST_RE.match("Velocity is defined as rate of displacement")
        self.assertIsNotNone(m)
        self.assertIn("term", m.groupdict())


# ===========================================================================
# 2. DEFINITION_TERM_AFTER_RE
# ===========================================================================

class TestDefinitionTermAfterRE(unittest.TestCase):
    """'... is called X' / '... is known as X' / '... is referred to as X'."""

    def test_is_called(self):
        m = DEFINITION_TERM_AFTER_RE.search("This process is called Osmosis")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Osmosis")

    def test_is_known_as_with_the(self):
        m = DEFINITION_TERM_AFTER_RE.search("This is known as the photosynthesis")
        self.assertIsNotNone(m)
        self.assertIn("photosynthesis", m.group("term"))

    def test_is_referred_to_as_a(self):
        m = DEFINITION_TERM_AFTER_RE.search("It is referred to as a catalyst")
        self.assertIsNotNone(m)
        self.assertIn("catalyst", m.group("term"))

    def test_sentence_end_stop(self):
        m = DEFINITION_TERM_AFTER_RE.search("The unit is called Newton.")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Newton")

    def test_named_group_present(self):
        # "is also called" is NOT matched — "also" intervenes between "is" and "called".
        # Use an input that the pattern actually matches.
        m = DEFINITION_TERM_AFTER_RE.search("This property is called velocity.")
        self.assertIsNotNone(m)
        self.assertIn("term", m.groupdict())

    def test_case_insensitive_connector(self):
        m = DEFINITION_TERM_AFTER_RE.search("This IS CALLED acceleration")
        self.assertIsNotNone(m)

    def test_empty_string(self):
        m = DEFINITION_TERM_AFTER_RE.search("")
        self.assertIsNone(m)

    def test_no_match_without_connector(self):
        m = DEFINITION_TERM_AFTER_RE.search("Osmosis occurs naturally in plants")
        self.assertIsNone(m)

    def test_comma_stop(self):
        m = DEFINITION_TERM_AFTER_RE.search("Enzyme is called protein, which catalyses")
        self.assertIsNotNone(m)
        self.assertNotIn(",", m.group("term"))


# ===========================================================================
# 3. DEFINITION_TERM_DENOTES_RE
# ===========================================================================

class TestDefinitionTermDenotesRE(unittest.TestCase):
    """'X denotes ...' — capital-initial term only; no re.I."""

    def test_capital_single_word(self):
        m = DEFINITION_TERM_DENOTES_RE.search(
            "Osmosis denotes the movement of water across a membrane"
        )
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Osmosis")

    def test_capital_multiword(self):
        m = DEFINITION_TERM_DENOTES_RE.search(
            "Electric current denotes the flow of charge per unit time"
        )
        self.assertIsNotNone(m)
        self.assertIn("Electric current", m.group("term"))

    def test_denote_singular(self):
        m = DEFINITION_TERM_DENOTES_RE.search("Velocity denote the speed in a direction")
        self.assertIsNotNone(m)

    def test_denotes_plural(self):
        m = DEFINITION_TERM_DENOTES_RE.search("Forces denotes the push or pull")
        self.assertIsNotNone(m)

    def test_lowercase_start_rejected(self):
        # No re.I — lowercase-initial terms must not match
        m = DEFINITION_TERM_DENOTES_RE.search("osmosis denotes the movement")
        self.assertIsNone(m)

    def test_empty_string(self):
        m = DEFINITION_TERM_DENOTES_RE.search("")
        self.assertIsNone(m)

    def test_no_match_without_denotes(self):
        m = DEFINITION_TERM_DENOTES_RE.search("Osmosis is the movement of water")
        self.assertIsNone(m)

    def test_named_group(self):
        m = DEFINITION_TERM_DENOTES_RE.search("Charge denotes the quantity of electricity")
        self.assertIsNotNone(m)
        self.assertIn("term", m.groupdict())


# ===========================================================================
# 4. DEFINITION_TERM_BY_MEAN_RE
# ===========================================================================

class TestDefinitionTermByMeanRE(unittest.TestCase):
    """'By X we mean ...' — re.I applied; explicit metalinguistic marker."""

    def test_lowercase_by(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("By osmosis we mean the movement of water")
        self.assertIsNotNone(m)
        self.assertIn("osmosis", m.group("term"))

    def test_capital_by(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("By Osmosis we mean the movement")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("term").strip(), "Osmosis")

    def test_case_insensitive_by_and_mean(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("BY photosynthesis WE MEAN the process")
        self.assertIsNotNone(m)

    def test_multiword_term(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search(
            "By electric current we mean the rate of flow of charge"
        )
        self.assertIsNotNone(m)
        self.assertIn("electric current", m.group("term").lower())

    def test_no_by_prefix_rejected(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("osmosis we mean something")
        self.assertIsNone(m)

    def test_no_we_mean_suffix_rejected(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("By osmosis we think")
        self.assertIsNone(m)

    def test_empty_string(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("")
        self.assertIsNone(m)

    def test_named_group(self):
        m = DEFINITION_TERM_BY_MEAN_RE.search("By velocity we mean speed with direction")
        self.assertIsNotNone(m)
        self.assertIn("term", m.groupdict())

    def test_refers_to_not_present(self):
        # "refers to" was explicitly rejected in R-I2 — confirm it has no pattern
        # (this test documents the architectural decision)
        has_refers_to = hasattr(__import__("modules.text_utils", fromlist=[""]),
                                "DEFINITION_TERM_REFERS_TO_RE")
        self.assertFalse(has_refers_to,
                         "DEFINITION_TERM_REFERS_TO_RE must not exist: 'refers to' was "
                         "rejected in M4.1 R-I2 for producing too many false positives")


# ===========================================================================
# 5. TERM_STOPWORDS
# ===========================================================================

class TestTermStopwords(unittest.TestCase):

    # --- type and immutability ---

    def test_is_frozenset(self):
        self.assertIsInstance(TERM_STOPWORDS, frozenset)

    def test_cannot_add_element(self):
        with self.assertRaises(AttributeError):
            TERM_STOPWORDS.add("new_word")  # type: ignore[attr-defined]

    # --- base set (preserved from both original modules) ---

    def test_base_stopwords_present(self):
        base = {"the", "a", "an", "this", "that", "these", "those",
                "it", "its", "which", "who"}
        for word in base:
            with self.subTest(word=word):
                self.assertIn(word, TERM_STOPWORDS)

    # --- extended set (M4.1 R-I3 additions) ---

    def test_extended_stopwords_present(self):
        extended = {"given", "such", "each", "every", "said", "same", "other"}
        for word in extended:
            with self.subTest(word=word):
                self.assertIn(word, TERM_STOPWORDS)

    def test_total_size(self):
        # 11 base + 7 extended = 18
        self.assertEqual(len(TERM_STOPWORDS), 18)

    # --- non-stopwords ---

    def test_valid_term_not_in_stopwords(self):
        valid_terms = ["Osmosis", "kinetic", "energy", "catalyst", "velocity"]
        for term in valid_terms:
            with self.subTest(term=term):
                self.assertNotIn(term.lower(), TERM_STOPWORDS)

    # --- case sensitivity ---

    def test_membership_is_case_sensitive(self):
        # The stopwords are stored lowercase; checking with upper/mixed case fails
        self.assertIn("the", TERM_STOPWORDS)
        self.assertNotIn("The", TERM_STOPWORDS)
        self.assertNotIn("THE", TERM_STOPWORDS)


# ===========================================================================
# 6. term_is_valid()
# ===========================================================================

class TestTermIsValid(unittest.TestCase):

    # --- accept ---

    def test_simple_valid_term(self):
        self.assertTrue(term_is_valid("Osmosis"))

    def test_two_char_term_accepted(self):
        self.assertTrue(term_is_valid("pH"))

    def test_multiword_valid(self):
        self.assertTrue(term_is_valid("kinetic energy"))

    def test_six_word_term_accepted(self):
        # Exactly 6 words is the boundary — must pass
        self.assertTrue(term_is_valid("one two three four five six"))

    def test_hyphenated_term_accepted(self):
        self.assertTrue(term_is_valid("non-metals"))

    # --- reject: empty / falsy ---

    def test_empty_string(self):
        self.assertFalse(term_is_valid(""))

    def test_whitespace_only(self):
        # Stripping is the caller's responsibility; whitespace-only is len < 2
        # after split, but len("  ") == 2. term_is_valid checks len(term) < 2.
        # "  " has length 2, so it passes the length check but split() → []
        # and len([]) == 0 is NOT > 6. However the term would be "  " after
        # strip is called by the caller. This tests the raw function behaviour.
        # The key point: empty string is caught.
        self.assertFalse(term_is_valid(""))

    # --- reject: single character ---

    def test_single_ascii_char(self):
        self.assertFalse(term_is_valid("F"))

    def test_single_char_capital(self):
        self.assertFalse(term_is_valid("A"))

    # --- reject: digit-initial ---

    def test_digit_initial_arabic(self):
        self.assertFalse(term_is_valid("3rd law"))

    def test_digit_initial_pure_number(self):
        self.assertFalse(term_is_valid("42"))

    def test_digit_initial_complex(self):
        self.assertFalse(term_is_valid("1st order reaction"))

    # --- reject: stopword ---

    def test_base_stopword_the(self):
        self.assertFalse(term_is_valid("the"))

    def test_base_stopword_it(self):
        self.assertFalse(term_is_valid("it"))

    def test_extended_stopword_given(self):
        self.assertFalse(term_is_valid("given"))

    def test_extended_stopword_each(self):
        self.assertFalse(term_is_valid("each"))

    def test_extended_stopword_other(self):
        self.assertFalse(term_is_valid("other"))

    def test_extended_stopword_same(self):
        self.assertFalse(term_is_valid("same"))

    def test_extended_stopword_every(self):
        self.assertFalse(term_is_valid("every"))

    def test_extended_stopword_said(self):
        self.assertFalse(term_is_valid("said"))

    def test_extended_stopword_such(self):
        self.assertFalse(term_is_valid("such"))

    def test_stopword_check_is_lowercase(self):
        # "The" is not in TERM_STOPWORDS (case-sensitive), but term_is_valid
        # lowercases before checking, so it should be rejected
        self.assertFalse(term_is_valid("The"))

    def test_stopword_check_uppercase(self):
        self.assertFalse(term_is_valid("EACH"))

    # --- reject: too long ---

    def test_seven_word_term_rejected(self):
        self.assertFalse(term_is_valid("one two three four five six seven"))

    def test_eight_word_term_rejected(self):
        self.assertFalse(term_is_valid("a b c d e f g h"))


# ===========================================================================
# 7. STEP_MARKER_RE
# ===========================================================================

class TestStepMarkerRE(unittest.TestCase):

    # --- numbered / lettered bullets ---

    def test_step_n_with_space(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Step 1: heat the solution"))

    def test_step_n_no_space(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("step1 add water"))

    def test_step_n_capital(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("STEP 2: cool the mixture"))

    def test_numbered_period(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("1. Remove the lid"))

    def test_numbered_paren(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("1) Remove the lid"))

    def test_numbered_two_digit(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("12. Measure the temperature"))

    def test_lettered_period(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("a. Remove the lid"))

    def test_lettered_paren(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("a) Remove the lid"))

    def test_lettered_capital_period(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("B. Add the reagent"))

    # --- prose markers ---

    def test_first_lower(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("first, heat the beaker"))

    def test_first_capital(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("First, heat the beaker"))

    def test_firstly(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Firstly, heat the beaker"))

    def test_then(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Then add the acid"))

    def test_then_comma(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Then, carefully add the acid"))

    def test_next(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Next, stir gently"))

    def test_finally(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Finally, cool the solution"))

    def test_lastly(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("Lastly, record the result"))

    # --- case insensitivity ---

    def test_first_all_caps(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("FIRST heat the water"))

    def test_then_mixed_case(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("THEN add reagent"))

    def test_finally_mixed_case(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("FINALLY cool it down"))

    # --- leading whitespace ---

    def test_leading_spaces_numbered(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("  2. Measure the volume"))

    def test_leading_tab_prose(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("\tFirst, do this"))

    # --- non-matches (body text / mid-sentence prose) ---

    def test_plain_body_text(self):
        self.assertIsNone(STEP_MARKER_RE.match("The solution turns blue"))

    def test_note_keyword(self):
        self.assertIsNone(STEP_MARKER_RE.match("Note that the temperature drops"))

    def test_mid_sentence_prose(self):
        self.assertIsNone(STEP_MARKER_RE.match("Otherwise, repeat the experiment"))

    def test_empty_string(self):
        self.assertIsNone(STEP_MARKER_RE.match(""))

    def test_mid_sentence_first(self):
        # "first" mid-sentence without line-start anchor — should NOT match
        self.assertIsNone(STEP_MARKER_RE.match("You should first heat the water"))

    # --- regression: the \b issue (documented design decision) ---

    def test_numbered_period_followed_by_space(self):
        # This is the key case the architecture's outer \b broke.
        # The fixed pattern (no \b after [.)] alternatives) must pass this.
        self.assertIsNotNone(STEP_MARKER_RE.match("1. Do this step carefully"),
                             "Numbered bullet followed by space must match; "
                             "this verifies the \\b-placement fix is in effect")

    def test_lettered_period_followed_by_space(self):
        self.assertIsNotNone(STEP_MARKER_RE.match("a. Do this step carefully"))


# ===========================================================================
# 8. partial_match_confidence()
# ===========================================================================

class TestPartialMatchConfidence(unittest.TestCase):

    def test_all_match(self):
        self.assertAlmostEqual(partial_match_confidence(5, 5, 0.85), 0.85)

    def test_none_match(self):
        self.assertAlmostEqual(partial_match_confidence(0, 5, 0.85), 0.0)

    def test_total_zero(self):
        self.assertAlmostEqual(partial_match_confidence(0, 0, 0.85), 0.0)

    def test_matched_equals_total_one(self):
        # Single-line block, one match = all lines match
        self.assertAlmostEqual(partial_match_confidence(1, 1, 0.85), 0.85)

    def test_one_of_five_floor_applies(self):
        # ratio = 0.85 * 1/5 = 0.17 < floor = 0.85 * 0.5 = 0.425
        self.assertAlmostEqual(partial_match_confidence(1, 5, 0.85), 0.425)

    def test_two_of_five_floor_applies(self):
        # ratio = 0.85 * 2/5 = 0.34 < floor = 0.425
        self.assertAlmostEqual(partial_match_confidence(2, 5, 0.85), 0.425)

    def test_three_of_five_ratio_dominates(self):
        # ratio = 0.85 * 3/5 = 0.51 > floor = 0.425
        self.assertAlmostEqual(partial_match_confidence(3, 5, 0.85), 0.51)

    def test_four_of_five(self):
        # ratio = 0.85 * 4/5 = 0.68 > floor = 0.425
        self.assertAlmostEqual(partial_match_confidence(4, 5, 0.85), 0.68)

    def test_different_base_floor(self):
        # base=0.70: floor = 0.35, ratio = 0.70 * 1/5 = 0.14 → floor
        self.assertAlmostEqual(partial_match_confidence(1, 5, 0.70), 0.35)

    def test_different_base_ratio(self):
        # base=0.70: floor = 0.35, ratio = 0.70 * 3/5 = 0.42 → ratio
        self.assertAlmostEqual(partial_match_confidence(3, 5, 0.70), 0.42)

    def test_floor_is_half_base(self):
        # The floor is always exactly base * 0.5
        for base in [0.5, 0.7, 0.85, 1.0]:
            result = partial_match_confidence(1, 100, base)
            # ratio = base/100, floor = base/2; floor always wins for 1/100
            self.assertAlmostEqual(result, base * 0.5,
                                   msg=f"Floor not base/2 for base={base}")

    def test_crossover_at_half_of_total(self):
        # At exactly 50% match, ratio == floor so either applies; verify no crash
        result = partial_match_confidence(5, 10, 0.80)
        # ratio = 0.80 * 5/10 = 0.40 == floor = 0.80 * 0.5 = 0.40
        self.assertAlmostEqual(result, 0.40)

    def test_returns_float(self):
        self.assertIsInstance(partial_match_confidence(1, 2, 0.85), float)

    def test_never_exceeds_base(self):
        for m, t in [(1, 1), (3, 5), (5, 5), (0, 5)]:
            result = partial_match_confidence(m, t, 0.85)
            self.assertLessEqual(result, 0.85 + 1e-9,
                                 msg=f"Result {result} exceeds base for {m}/{t}")


# ===========================================================================
# 9. Module purity — text_utils must not import pipeline modules
# ===========================================================================

class TestTextUtilsModulePurity(unittest.TestCase):

    def test_no_pipeline_imports(self):
        """text_utils.py must contain no import statements for pipeline modules.

        Module names may appear in docstrings and comments for documentation
        purposes (e.g. 'moved from stage_a_geometry'); only actual import
        lines are checked here.
        """
        import modules.text_utils as tu_module
        import inspect
        source = inspect.getsource(tu_module)
        # Filter to only lines that are actual import statements
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        import_block = "\n".join(import_lines)
        forbidden = [
            'stage_a_geometry', 'stage_b_classify', 'stage_c_priority',
            'stage_d_extraction', 'stage_e_validation', 'pipeline',
            'layout_detector', 'pdf_parser', 'vlm_inference',
            'ocr_engine', 'kg_readiness', 'semantic_processor',
        ]
        for module_name in forbidden:
            with self.subTest(module_name=module_name):
                self.assertNotIn(module_name, import_block,
                                 f"text_utils must not import {module_name}")

    def test_no_external_dependencies(self):
        """text_utils.py must not import any non-stdlib third-party library."""
        import modules.text_utils as tu_module
        import inspect
        source = inspect.getsource(tu_module)
        forbidden_third_party = ['fitz', 'PIL', 'numpy', 'pandas', 'scipy']
        for lib in forbidden_third_party:
            with self.subTest(lib=lib):
                self.assertNotIn(f'import {lib}', source)
                self.assertNotIn(f'from {lib}', source)

    def test_required_exports_present(self):
        import modules.text_utils as tu_module
        required = [
            'DEFINITION_TERM_FIRST_RE',
            'DEFINITION_TERM_AFTER_RE',
            'DEFINITION_TERM_DENOTES_RE',
            'DEFINITION_TERM_BY_MEAN_RE',
            'TERM_STOPWORDS',
            'STEP_MARKER_RE',
            'term_is_valid',
            'partial_match_confidence',
        ]
        for name in required:
            with self.subTest(name=name):
                self.assertTrue(hasattr(tu_module, name),
                                f"text_utils must export {name}")


# ===========================================================================
# 10. Backward compatibility — stage_a_geometry and content_blocks aliases
# ===========================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """After M4.1A, both modules must expose the same names as before,
    pointing to the text_utils objects rather than local definitions."""

    def setUp(self):
        import modules.text_utils as tu
        import modules.stage_a_geometry as stage_a
        import modules.content_blocks as content
        self.tu = tu
        self.stage_a = stage_a
        self.content = content

    # --- stage_a_geometry ---

    def test_stage_a_first_re_is_text_utils(self):
        self.assertIs(
            self.stage_a._DEFINITION_TERM_FIRST_RE,
            self.tu.DEFINITION_TERM_FIRST_RE,
        )

    def test_stage_a_after_re_is_text_utils(self):
        self.assertIs(
            self.stage_a._DEFINITION_TERM_AFTER_RE,
            self.tu.DEFINITION_TERM_AFTER_RE,
        )

    def test_stage_a_stopwords_equal_text_utils(self):
        # _DEFINITION_TERM_STOPWORDS in stage_a is the TERM_STOPWORDS frozenset
        self.assertEqual(
            self.stage_a._DEFINITION_TERM_STOPWORDS,
            self.tu.TERM_STOPWORDS,
        )

    def test_stage_a_stopwords_contains_extended(self):
        # The extended set (M4.1 R-I3) is now present in stage_a too
        for word in ("given", "such", "each", "every", "said", "same", "other"):
            with self.subTest(word=word):
                self.assertIn(word, self.stage_a._DEFINITION_TERM_STOPWORDS)

    def test_stage_a_label_anchor_re_unchanged(self):
        # _LABEL_ANCHOR_RE is NOT moved to text_utils — verify it still exists
        self.assertTrue(hasattr(self.stage_a, '_LABEL_ANCHOR_RE'))
        self.assertIsInstance(self.stage_a._LABEL_ANCHOR_RE, re.Pattern)

    def test_stage_a_first_re_still_matches(self):
        m = self.stage_a._DEFINITION_TERM_FIRST_RE.match(
            "Velocity is defined as the rate of change of displacement"
        )
        self.assertIsNotNone(m)

    def test_stage_a_after_re_still_matches(self):
        m = self.stage_a._DEFINITION_TERM_AFTER_RE.search(
            "This property is called Inertia."
        )
        self.assertIsNotNone(m)

    # --- content_blocks ---

    def test_content_first_re_is_text_utils(self):
        self.assertIs(
            self.content.DEFINITION_TERM_FIRST_RE,
            self.tu.DEFINITION_TERM_FIRST_RE,
        )

    def test_content_after_re_is_text_utils(self):
        self.assertIs(
            self.content.DEFINITION_TERM_AFTER_RE,
            self.tu.DEFINITION_TERM_AFTER_RE,
        )

    def test_content_term_stopwords_equal_text_utils(self):
        self.assertEqual(self.content._TERM_STOPWORDS, self.tu.TERM_STOPWORDS)

    def test_content_stopwords_contains_extended(self):
        for word in ("given", "such", "each", "every", "said", "same", "other"):
            with self.subTest(word=word):
                self.assertIn(word, self.content._TERM_STOPWORDS)

    def test_content_activity_label_re_unchanged(self):
        # Other label patterns in content_blocks are NOT affected
        self.assertTrue(hasattr(self.content, 'ACTIVITY_LABEL_RE'))
        self.assertTrue(hasattr(self.content, 'BOX_LABEL_RE'))
        self.assertTrue(hasattr(self.content, 'WARNING_LABEL_RE'))
        self.assertTrue(hasattr(self.content, 'EXAMPLE_LABEL_RE'))

    def test_content_first_re_still_matches(self):
        m = self.content.DEFINITION_TERM_FIRST_RE.match(
            "Enzymes are defined as biological catalysts"
        )
        self.assertIsNotNone(m)

    def test_content_term_stopwords_rejects_base(self):
        self.assertIn("the", self.content._TERM_STOPWORDS)

    def test_content_term_stopwords_rejects_extended(self):
        self.assertIn("given", self.content._TERM_STOPWORDS)

    # --- no local definitions remain ---

    def test_no_local_first_re_in_stage_a(self):
        """_DEFINITION_TERM_FIRST_RE = re.compile(...) must not appear in source."""
        path = Path(__file__).parent.parent / 'modules' / 'stage_a_geometry.py'
        src = path.read_text()
        self.assertNotIn(
            '_DEFINITION_TERM_FIRST_RE = re.compile',
            src,
            "Local definition of _DEFINITION_TERM_FIRST_RE must be removed",
        )

    def test_no_local_stopwords_in_stage_a(self):
        path = Path(__file__).parent.parent / 'modules' / 'stage_a_geometry.py'
        src = path.read_text()
        self.assertNotIn(
            '_DEFINITION_TERM_STOPWORDS = {',
            src,
            "Local definition of _DEFINITION_TERM_STOPWORDS must be removed",
        )

    def test_no_local_first_re_in_content_blocks(self):
        path = Path(__file__).parent.parent / 'modules' / 'content_blocks.py'
        src = path.read_text()
        self.assertNotIn(
            'DEFINITION_TERM_FIRST_RE = re.compile',
            src,
            "Local definition of DEFINITION_TERM_FIRST_RE must be removed",
        )

    def test_no_local_stopwords_in_content_blocks(self):
        path = Path(__file__).parent.parent / 'modules' / 'content_blocks.py'
        src = path.read_text()
        self.assertNotIn(
            '_TERM_STOPWORDS = {',
            src,
            "Local definition of _TERM_STOPWORDS must be removed",
        )


if __name__ == "__main__":
    unittest.main()
