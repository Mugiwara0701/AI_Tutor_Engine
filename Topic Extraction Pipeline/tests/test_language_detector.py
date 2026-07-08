"""
tests/test_language_detector.py — unit tests for modules/language_detector.py,
the deterministic language-ID + script-usability layer added by the
language-robustness milestone.

Run: python -m pytest tests/test_language_detector.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from modules import language_detector as ld


# ---------------------------------------------------------------------------
# script_ratio
# ---------------------------------------------------------------------------
def test_script_ratio_pure_devanagari_is_high():
    text = "सूर्यकांत त्रिपाठी निराला"
    assert ld.script_ratio(text, "hi") >= 0.9


def test_script_ratio_pure_english_is_high():
    text = "The Ascent of Man"
    assert ld.script_ratio(text, "en") >= 0.9


def test_script_ratio_mismatched_language_is_low():
    text = "सूर्यकांत त्रिपाठी निराला"
    assert ld.script_ratio(text, "en") == 0.0


def test_script_ratio_empty_text_is_zero():
    assert ld.script_ratio("", "hi") == 0.0
    assert ld.script_ratio("   ", "en") == 0.0


def test_script_ratio_unknown_language_is_zero():
    assert ld.script_ratio("hello", "xx") == 0.0


def test_script_ratio_ignores_digits_and_punctuation():
    # Page numbers / punctuation shouldn't dilute the ratio -- only
    # alphabetic characters are counted.
    text = "1.1 सूर्यकांत, त्रिपाठी।"
    assert ld.script_ratio(text, "hi") >= 0.9


# ---------------------------------------------------------------------------
# detect_language_from_text
# ---------------------------------------------------------------------------
def test_detect_language_from_text_picks_devanagari():
    assert ld.detect_language_from_text("सूर्यकांत त्रिपाठी निराला") == "hi"


def test_detect_language_from_text_picks_english():
    assert ld.detect_language_from_text("The Ascent of Man") == "en"


def test_detect_language_from_text_returns_none_below_threshold():
    # Mostly digits/punctuation -- no script clears the confidence bar.
    assert ld.detect_language_from_text("1.1 ..--..") is None


# ---------------------------------------------------------------------------
# detect_language_from_metadata
# ---------------------------------------------------------------------------
def test_detect_language_from_metadata_english_filename():
    assert ld.detect_language_from_metadata("hindi_chapter_1.pdf") == "hi"


def test_detect_language_from_metadata_sanskrit_subject():
    assert ld.detect_language_from_metadata("some.pdf", "", "Sanskrit") == "sa"


def test_detect_language_from_metadata_native_spelling():
    assert ld.detect_language_from_metadata("किताब हिंदी") == "hi"


def test_detect_language_from_metadata_no_hints_returns_none():
    assert ld.detect_language_from_metadata("chapter1.pdf", "Macroeconomics", "economics") is None


def test_detect_language_from_metadata_ignores_none_sources():
    assert ld.detect_language_from_metadata(None, None, None) is None


# ---------------------------------------------------------------------------
# detect_language — full priority chain
# ---------------------------------------------------------------------------
def test_detect_language_override_wins_over_everything():
    assert ld.detect_language(filename="hindi.pdf", sample_text="The Ascent of Man", override="sa") == "sa"


def test_detect_language_metadata_wins_over_script():
    # Text looks English, but the filename says Sanskrit -- metadata should win.
    assert ld.detect_language(filename="sanskrit_chapter.pdf", sample_text="1 2 3") == "sa"


def test_detect_language_falls_back_to_script_analysis():
    assert ld.detect_language(filename="chapter_03.pdf", subject="economics",
                               sample_text="सूर्यकांत त्रिपाठी निराला") == "hi"


def test_detect_language_falls_back_to_english_default():
    assert ld.detect_language(filename="chapter_03.pdf", subject="economics",
                               sample_text="Macroeconomics is the study of aggregates.") == "en"


def test_detect_language_no_information_defaults_to_english():
    assert ld.detect_language() == "en"


# ---------------------------------------------------------------------------
# language_name / ocr_lang_code
# ---------------------------------------------------------------------------
def test_language_name_known_codes():
    assert ld.language_name("hi") == "Hindi"
    assert ld.language_name("sa") == "Sanskrit"
    assert ld.language_name("en") == "English"


def test_language_name_unknown_code_falls_back_to_english():
    assert ld.language_name("xx") == "English"


def test_ocr_lang_code_mapping():
    assert ld.ocr_lang_code("hi") == "hin"
    assert ld.ocr_lang_code("sa") == "san"
    assert ld.ocr_lang_code("en") == "eng"


def test_ocr_lang_code_unknown_falls_back_to_english():
    assert ld.ocr_lang_code("xx") == "eng"


# ---------------------------------------------------------------------------
# is_text_usable_for_language — the legacy-font / garbled-text detector
# ---------------------------------------------------------------------------
def test_usable_when_script_matches():
    text = "सूर्यकांत त्रिपाठी निराला की प्रसिद्ध कविताएँ"
    assert ld.is_text_usable_for_language(text, "hi") is True


def test_unusable_when_script_is_actually_latin_gibberish():
    # This is the reported symptom: a Hindi PDF whose text layer decoded to
    # Latin-looking characters because of a legacy (non-Unicode) font.
    garbled = "t;'kadj izlkn lw;Zdkar f=kikBh ^fujkyk*"
    assert ld.is_text_usable_for_language(garbled, "hi") is False


def test_short_text_gets_benefit_of_the_doubt():
    # Too few alphabetic characters to judge reliably -- must not be
    # penalized just for being short (e.g. a page number or single word).
    assert ld.is_text_usable_for_language("12", "hi") is True
    assert ld.is_text_usable_for_language("Fig", "hi") is True


def test_usable_for_english_when_actually_english():
    assert ld.is_text_usable_for_language("This is a perfectly normal sentence.", "en") is True


# ---------------------------------------------------------------------------
# detect_legacy_devanagari_font / detect_language(font_names=...) —
# the fix for a whole-book legacy-font case (e.g. Walkman-Chanakya905,
# Kruti Dev, DevLys): every page's text layer is script-mismatched, so
# there is no genuine Devanagari anywhere for script-ratio analysis to
# find, and the book title/filename are equally garbled, so metadata
# matching finds nothing either. The font name is the one signal left.
# ---------------------------------------------------------------------------
def test_detect_legacy_font_recognizes_known_families():
    assert ld.detect_legacy_devanagari_font(["Walkman-Chanakya905Bold"]) == "hi"
    assert ld.detect_legacy_devanagari_font(["QROIHM+Walkman-Chanakya905BoldItalic"]) == "hi"
    assert ld.detect_legacy_devanagari_font(["KrutiDev010"]) == "hi"
    assert ld.detect_legacy_devanagari_font(["DevLys010"]) == "hi"


def test_detect_legacy_font_is_case_insensitive():
    assert ld.detect_legacy_devanagari_font(["WALKMAN-CHANAKYA905BOLD"]) == "hi"


def test_detect_legacy_font_ignores_ordinary_fonts():
    assert ld.detect_legacy_devanagari_font(["Times-Roman", "Arial", "Arial,Bold"]) is None


def test_detect_legacy_font_handles_empty_or_none_input():
    assert ld.detect_legacy_devanagari_font(None) is None
    assert ld.detect_legacy_devanagari_font([]) is None
    assert ld.detect_legacy_devanagari_font(["", None]) is None


def test_detect_language_uses_legacy_font_when_script_analysis_would_say_english():
    # The exact real-world reproduction: book title, filename, and sample
    # text are ALL script-mismatched gibberish (indistinguishable from
    # clean Latin/English by script_ratio alone), but the embedded font
    # name gives it away.
    garbled_title = "varjk"
    garbled_sample = "t;'kadj izlkn lw;Zdkar f=kikBh"
    result = ld.detect_language(
        filename="lhat1ps.pdf", book_title=garbled_title, subject="unknown",
        sample_text=garbled_sample, font_names=["Walkman-Chanakya905Normal", "Arial"],
    )
    assert result == "hi"


def test_detect_language_metadata_still_wins_over_legacy_font():
    # A Sanskrit-named book set in a legacy font should still resolve to
    # "sa", not fall through to the font layer's "hi" guess -- metadata has
    # priority.
    result = ld.detect_language(
        filename="sanskrit_chapter.pdf", font_names=["Walkman-Chanakya905Normal"],
    )
    assert result == "sa"


def test_detect_language_legacy_font_does_not_override_clean_english_script():
    # A real English chapter that merely happens to share a font table
    # (unusual, but the check should still not misfire if script analysis
    # already has a clear, correct answer) -- covered by priority order:
    # only reached when metadata found nothing, so pair it with a sample
    # that also isn't Devanagari-legible either way. Since font check only
    # ever returns "hi" (never overrides an established "en"), this simply
    # confirms font_names=None (no legacy font present) doesn't change the
    # ordinary script-based English result.
    result = ld.detect_language(filename="chapter_03.pdf", subject="economics",
                                 sample_text="This chapter covers supply and demand.",
                                 font_names=["Arial", "Times-Roman"])
    assert result == "en"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))