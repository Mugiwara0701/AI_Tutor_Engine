"""
tests/test_ocr_cleanup.py — regression tests for modules/ocr_cleanup.py
(Phase 1 Stabilization Sprint — final refinement, Finding 1).

ROOT CAUSE COVERED: the independent audit found NO dedicated OCR
content-cleanup stage anywhere in the pipeline -- only Unicode
normalization (NFC + invisible-char strip, pdf_parser.clean_extracted_text)
and JSON-parseability escape repair (modules/json_repair.py) existed.
Neither addresses OCR-specific content-quality artifacts: broken
ligatures, duplicate/irregular whitespace, OCR punctuation-spacing noise,
or words merged together with a dropped space.

This file tests the new modules/ocr_cleanup.py stage:
  1. Broken ligature decomposition (fi/fl/ffi/ffl/... presentation forms).
  2. Duplicate/irregular whitespace collapse.
  3. OCR punctuation-spacing cleanup.
  4. Merged-word repair at a case-transition boundary.
  5. Idempotency of the full clean_ocr_text() pipeline.
  6. Language-independence: identical behavior contract across Hindi,
     Sanskrit, Tamil, and mixed-script input -- no script has its visible
     characters altered, no language is special-cased in the code.
  7. Robustness: never raises, degrades to input on empty/odd input.
  8. Integration: modules/ocr_engine.py actually calls clean_ocr_text() on
     the tesseract output path.
"""
from __future__ import annotations

import pytest

from modules.ocr_cleanup import (
    clean_ocr_text,
    fix_broken_ligatures,
    collapse_duplicate_whitespace,
    normalize_ocr_punctuation,
    split_merged_words_at_case_boundary,
)


# ---------------------------------------------------------------------------
# 1. Broken ligatures
# ---------------------------------------------------------------------------
class TestBrokenLigatures:
    def test_fi_ligature_decomposed(self):
        assert fix_broken_ligatures("con\ufb01dence") == "confidence"

    def test_fl_ligature_decomposed(self):
        assert fix_broken_ligatures("re\ufb02ection") == "reflection"

    def test_ffi_ligature_decomposed(self):
        assert fix_broken_ligatures("e\ufb03ciency") == "efficiency"

    def test_no_ligature_present_unchanged(self):
        assert fix_broken_ligatures("efficiency") == "efficiency"

    def test_devanagari_text_unaffected(self):
        text = "क्षितिज विज्ञान"
        assert fix_broken_ligatures(text) == text

    def test_empty_and_none_safe(self):
        assert fix_broken_ligatures("") == ""
        assert fix_broken_ligatures(None) is None


# ---------------------------------------------------------------------------
# 2. Duplicate / irregular whitespace
# ---------------------------------------------------------------------------
class TestWhitespaceCollapse:
    def test_multiple_spaces_collapse_to_one(self):
        assert collapse_duplicate_whitespace("word1    word2") == "word1 word2"

    def test_tabs_collapse(self):
        assert collapse_duplicate_whitespace("word1\t\tword2") == "word1 word2"

    def test_nonbreaking_space_collapsed(self):
        assert collapse_duplicate_whitespace("word1\u00a0\u00a0word2") == "word1 word2"

    def test_mixed_space_and_tab(self):
        assert collapse_duplicate_whitespace("word1 \t word2") == "word1 word2"

    def test_leading_trailing_whitespace_stripped(self):
        assert collapse_duplicate_whitespace("   word1 word2   ") == "word1 word2"

    def test_single_space_unchanged(self):
        assert collapse_duplicate_whitespace("word1 word2") == "word1 word2"

    def test_devanagari_whitespace_collapse(self):
        assert collapse_duplicate_whitespace("क्षितिज    विज्ञान") == "क्षितिज विज्ञान"

    def test_newline_alone_preserved_not_collapsed_to_space(self):
        # A lone newline is a structural break, not OCR noise -- only runs
        # of pure horizontal whitespace get collapsed.
        result = collapse_duplicate_whitespace("line1\nline2")
        assert "\n" in result

    def test_idempotent(self):
        text = "word1     word2  \t  word3"
        once = collapse_duplicate_whitespace(text)
        twice = collapse_duplicate_whitespace(once)
        assert once == twice

    def test_empty_and_none_safe(self):
        assert collapse_duplicate_whitespace("") == ""
        assert collapse_duplicate_whitespace(None) is None


# ---------------------------------------------------------------------------
# 3. OCR punctuation spacing
# ---------------------------------------------------------------------------
class TestPunctuationNormalization:
    def test_removes_space_before_comma(self):
        assert normalize_ocr_punctuation("word1 , word2") == "word1, word2"

    def test_removes_space_before_semicolon(self):
        assert normalize_ocr_punctuation("word1 ; word2") == "word1; word2"

    def test_removes_space_before_closing_paren(self):
        assert normalize_ocr_punctuation("(example )") == "(example)"

    def test_collapses_duplicated_commas(self):
        assert normalize_ocr_punctuation("word1,, word2") == "word1, word2"

    def test_collapses_duplicated_semicolons(self):
        assert normalize_ocr_punctuation("word1;; word2") == "word1; word2"

    def test_inserts_missing_space_after_comma(self):
        assert normalize_ocr_punctuation("word1,word2") == "word1, word2"

    def test_inserts_missing_space_after_semicolon(self):
        assert normalize_ocr_punctuation("word1;word2") == "word1; word2"

    def test_ellipsis_not_collapsed(self):
        # '.' is deliberately excluded from duplicate-punctuation collapse.
        assert normalize_ocr_punctuation("wait...") == "wait..."

    def test_decimal_number_not_corrupted(self):
        # '.' spacing/merging is out of scope precisely to protect this.
        assert normalize_ocr_punctuation("3.14") == "3.14"

    def test_question_exclamation_not_collapsed(self):
        assert normalize_ocr_punctuation("Really?!") == "Really?!"

    def test_devanagari_punctuation_spacing(self):
        assert normalize_ocr_punctuation("विज्ञान , गणित") == "विज्ञान, गणित"

    def test_idempotent(self):
        text = "word1 , word2,,word3"
        once = normalize_ocr_punctuation(text)
        twice = normalize_ocr_punctuation(once)
        assert once == twice

    def test_empty_and_none_safe(self):
        assert normalize_ocr_punctuation("") == ""
        assert normalize_ocr_punctuation(None) is None


# ---------------------------------------------------------------------------
# 4. Merged words at a case-transition boundary
# ---------------------------------------------------------------------------
class TestMergedWordSplit:
    def test_lowercase_to_uppercase_boundary_split(self):
        result = split_merged_words_at_case_boundary("photosynthesisRequires")
        assert result == "photosynthesis Requires"

    def test_digit_to_uppercase_boundary_split(self):
        result = split_merged_words_at_case_boundary("Chapter1Introduction")
        assert result == "Chapter1 Introduction"

    def test_no_boundary_unchanged(self):
        assert split_merged_words_at_case_boundary("Photosynthesis") == "Photosynthesis"

    def test_all_lowercase_unchanged(self):
        assert split_merged_words_at_case_boundary("photosynthesis") == "photosynthesis"

    def test_devanagari_has_no_case_never_altered(self):
        # Devanagari has no case distinction, so this heuristic structurally
        # never fires on it -- not because of a language-specific branch,
        # but because .isupper()/.islower() are both False for these
        # characters.
        text = "क्षितिजविज्ञान"
        assert split_merged_words_at_case_boundary(text) == text

    def test_does_not_split_inside_opening_bracket_quote(self):
        # prev char is an opening delimiter -- not a genuine merge.
        result = split_merged_words_at_case_boundary('("Example")')
        assert result == '("Example")'

    def test_idempotent(self):
        text = "wordOne wordTwo"
        once = split_merged_words_at_case_boundary(text)
        twice = split_merged_words_at_case_boundary(once)
        assert once == twice

    def test_empty_and_none_safe(self):
        assert split_merged_words_at_case_boundary("") == ""
        assert split_merged_words_at_case_boundary(None) is None


# ---------------------------------------------------------------------------
# 5. Full pipeline: clean_ocr_text()
# ---------------------------------------------------------------------------
class TestCleanOcrTextPipeline:
    def test_combines_all_stages(self):
        raw = "The  con\ufb01dence   level was high ,and risingNext chapter follows."
        result = clean_ocr_text(raw)
        assert "\ufb01" not in result          # ligature decomposed
        assert "confidence" in result
        assert "  " not in result              # no double spaces left
        assert " ,and" not in result           # no space before comma
        # merged words at a case boundary get a space
        assert "rising Next" in result

    def test_idempotent_on_realistic_ocr_output(self):
        raw = "Photosynthesis  is  the  process ,by which  plants con\ufb01dence  make food.NextTopic starts here."
        once = clean_ocr_text(raw)
        twice = clean_ocr_text(once)
        assert once == twice

    def test_hindi_text_language_preserved(self):
        raw = "क्षितिज   विज्ञान"
        result = clean_ocr_text(raw)
        assert "क्षितिज" in result
        assert "विज्ञान" in result
        assert "Kshitij" not in result
        assert "Vigyan" not in result

    def test_sanskrit_text_language_preserved(self):
        raw = "संधि  शब्द रूप"
        result = clean_ocr_text(raw)
        assert "संधि" in result
        assert "शब्द" in result

    def test_tamil_text_language_preserved(self):
        raw = "தமிழ்   மொழி"
        result = clean_ocr_text(raw)
        assert "தமிழ்" in result
        assert "மொழி" in result

    def test_mixed_language_book_content_preserved(self):
        raw = "Chapter 1: क्षितिज  (Hindi Poetry)"
        result = clean_ocr_text(raw)
        assert "क्षितिज" in result
        assert "Chapter" in result

    def test_english_content_cleaned_normally(self):
        raw = "This   book covers  photosynthesis ,respiration ,and growth."
        result = clean_ocr_text(raw)
        assert "  " not in result
        assert " ,respiration" not in result

    def test_no_conditional_branches_on_language_or_book_name(self):
        # Script/language names may legitimately appear in comments and
        # docstrings for explanation (as they do throughout this
        # codebase) -- what must NOT exist is a conditional branch that
        # special-cases a specific language, script, or book title.
        import inspect
        import modules.ocr_cleanup as mod
        source = inspect.getsource(mod)
        forbidden_conditionals = [
            "== \"hindi\"", "== 'hindi'", "== \"sanskrit\"", "== 'sanskrit'",
            "== \"tamil\"", "== 'tamil'", "kshitij", "\"ncert\"", "'ncert'",
        ]
        lowered = source.lower()
        for term in forbidden_conditionals:
            assert term not in lowered, f"found language/book-specific branch: {term}"

    def test_never_raises_on_odd_input(self):
        clean_ocr_text("\x00\x01 mixed \ud800 text")

    def test_empty_and_none_safe(self):
        assert clean_ocr_text("") == ""
        assert clean_ocr_text(None) is None

    def test_repeated_full_pipeline_call_is_stable(self):
        raw = "word1,,word2   word3ThirdWord con\ufb01dent"
        results = [clean_ocr_text(raw)]
        for _ in range(3):
            results.append(clean_ocr_text(results[-1]))
        assert len(set(results[1:])) == 1  # stable after first pass


# ---------------------------------------------------------------------------
# 6. Integration: ocr_engine wires clean_ocr_text() into the tesseract path
# ---------------------------------------------------------------------------
class TestOcrEngineIntegration:
    def test_ocr_engine_imports_clean_ocr_text(self):
        import modules.ocr_engine as ocr_engine
        assert hasattr(ocr_engine, "clean_ocr_text")

    def test_ocr_engine_source_calls_clean_ocr_text(self):
        import inspect
        import modules.ocr_engine as ocr_engine
        source = inspect.getsource(ocr_engine._tesseract_ocr_page)
        assert "clean_ocr_text(" in source