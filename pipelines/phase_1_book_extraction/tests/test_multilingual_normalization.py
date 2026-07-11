"""
tests/test_multilingual_normalization.py — regression tests for the
Phase 1 Stabilization Sprint (Unicode, Multilingual, LaTeX & Canonical
Normalization), run on top of frozen Phases A-E.

ROOT CAUSE COVERED: modules/pdf_parser.py::slugify() used to keep ONLY
ASCII a-z/0-9 (`re.sub(r"[^a-z0-9]+", "-", raw)`), silently destroying
any non-Latin-script title (Hindi, Sanskrit, Tamil, ...) -- collapsing
it to "" -> "untitled". Because make_id()/make_urn()/book folder
naming/chapter filenames are all layered on slugify(), this produced
both (a) folder/file names that lost the book's actual language, and
(b) real content-addressed-identity collisions: two DIFFERENT
non-Latin titles both slugified to the same leftover fragments and
therefore hashed to the same id/urn.

This file tests, additively, only what the sprint's fix touches:
  1. slugify() preserves every script (Hindi/Devanagari, Sanskrit,
     Tamil, mixed-language, plain English) instead of transliterating,
     romanizing, or dropping it.
  2. make_id()/make_urn() no longer collide for two distinct
     non-Latin titles.
  3. The full book/chapter folder-path pipeline (pdf_parser.slugify ->
     storage.utils.normalize_path_component -> storage.path_resolver
     .PathResolver) preserves the original script end-to-end.
  4. clean_extracted_text()'s Unicode-normalization layer canonicalizes
     equivalent representations and strips genuinely invisible
     characters without altering any visible/language content.
  5. Existing English/ASCII slugify() behavior is unchanged (no
     regression for the common case).
  6. LaTeX / escape-sequence normalization (modules/json_repair.py) --
     already a mature, general-purpose pipeline pre-sprint -- continues
     to behave deterministically and is not book-specific.

Per this codebase's own testing convention (see e.g.
tests/test_phase_a_finalization.py), these are pure unit/regression
tests: no PDF/network/model calls.
"""
from __future__ import annotations

import unicodedata

import pytest

from modules.pdf_parser import slugify, make_id, make_urn, clean_extracted_text
from storage.utils import normalize_path_component
from storage.path_resolver import PathResolver
import modules.json_repair as json_repair


# ---------------------------------------------------------------------------
# 1. slugify() preserves every script -- never transliterates/romanizes
# ---------------------------------------------------------------------------

HINDI_BOOK_TITLES = ["विज्ञान", "क्षितिज"]
SANSKRIT_TERMS = ["संधि", "शब्द रूप"]
TAMIL_TITLE = "தமிழ்"
ENGLISH_TITLE = "Chapter 1: Photosynthesis"


class TestSlugifyPreservesScript:
    @pytest.mark.parametrize("title", HINDI_BOOK_TITLES)
    def test_hindi_title_preserved_verbatim(self, title):
        assert slugify(title) == title

    @pytest.mark.parametrize("title", SANSKRIT_TERMS)
    def test_sanskrit_title_preserved(self, title):
        # Sanskrit here is written in Devanagari (as NCERT books print it);
        # the whole word/phrase must survive, only whitespace collapsing
        # to '-'.
        assert slugify(title) == title.replace(" ", "-")

    def test_tamil_title_preserved_verbatim(self):
        assert slugify(TAMIL_TITLE) == TAMIL_TITLE

    def test_mixed_language_title_preserves_both_scripts(self):
        result = slugify("Mixed हिंदी and English")
        assert "हिंदी" in result
        assert "mixed" in result
        assert "english" in result

    def test_never_falls_back_to_untitled_for_real_non_latin_content(self):
        for title in HINDI_BOOK_TITLES + SANSKRIT_TERMS + [TAMIL_TITLE]:
            assert slugify(title) != "untitled"

    def test_devanagari_conjuncts_and_vowel_signs_not_fragmented(self):
        """Regression guard for the isalnum()-only pitfall: Devanagari
        combining vowel signs / virama (Unicode category Mn/Mc -- e.g. the
        sign making 'कि' out of 'क' + 'ि', or the virama forming a
        conjunct like 'ज्ञ') are NOT alphanumeric by Python's own
        str.isalnum(), but must never be treated as a word-separator, or
        the script visually shatters into disconnected consonants."""
        result = slugify("क्षितिज")
        # No stray '-' was inserted inside the word.
        assert "-" not in result
        assert result == "क्षितिज"

    def test_empty_or_whitespace_only_falls_back_to_untitled(self):
        assert slugify("") == "untitled"
        assert slugify("   ") == "untitled"
        assert slugify(None) == "untitled"


class TestSlugifyEnglishBehaviorUnchanged:
    """Pre-sprint ASCII/English behavior must be unaffected."""

    def test_basic_english_slug(self):
        assert slugify("Chapter 1: Photosynthesis") == "chapter-1-photosynthesis"

    def test_multi_part_join(self):
        assert slugify("Some Chapter", "concept", "Photosynthesis") == \
            "some-chapter-concept-photosynthesis"

    def test_case_insensitive(self):
        assert slugify("Photosynthesis") == slugify("photosynthesis")

    def test_punctuation_collapses_to_single_hyphen(self):
        assert slugify("Hello,   World!!!") == "hello-world"


# ---------------------------------------------------------------------------
# 2. make_id()/make_urn() no longer collide across distinct non-Latin titles
# ---------------------------------------------------------------------------

class TestIdentityNoLongerCollidesForNonLatinTitles:
    def test_two_distinct_hindi_titles_produce_distinct_ids(self):
        id1 = make_id("राष्ट्रीय आय का लेखांकन", "concept", "GDP")
        id2 = make_id("संधि विच्छेद के नियम", "concept", "GDP")
        assert id1 != id2

    def test_two_distinct_hindi_titles_produce_distinct_urns(self):
        urn1 = make_urn("book:chapter", "concept", "विज्ञान")
        urn2 = make_urn("book:chapter", "concept", "क्षितिज")
        assert urn1 != urn2

    def test_id_is_still_deterministic_for_non_latin_input(self):
        a = make_id("क्षितिज", "concept", "GDP")
        b = make_id("क्षितिज", "concept", "GDP")
        assert a == b

    def test_id_slug_prefix_contains_original_script(self):
        result = make_id("विज्ञान")
        slug_part, _, hash_part = result.rpartition("-")
        assert "विज्ञान" in slug_part
        assert len(hash_part) == 6


# ---------------------------------------------------------------------------
# 3. Full folder-path pipeline preserves original script end-to-end
# ---------------------------------------------------------------------------

class TestFolderPathPreservesOriginalScript:
    def test_book_slug_survives_path_component_normalization(self):
        book_slug = slugify("विज्ञान")
        assert normalize_path_component(book_slug) == "विज्ञान"

    def test_full_path_resolver_preserves_hindi_book_and_subject(self):
        resolver = PathResolver()
        path = resolver.resolve("CBSE", "9", "हिंदी", slugify("क्षितिज"))
        assert path == "AI_TUTOR/CBSE/Class_9/हिंदी/क्षितिज"
        assert "Kshitij" not in path
        assert "Hindi" not in path or "हिंदी" in path

    def test_full_path_resolver_preserves_sanskrit(self):
        resolver = PathResolver()
        path = resolver.resolve("CBSE", "10", "संस्कृत", slugify("संधि"))
        assert path.endswith("/संस्कृत/संधि")

    def test_english_book_path_unaffected(self):
        resolver = PathResolver()
        path = resolver.resolve("CBSE", "12", "Chemistry", slugify("Chemistry Part 1"))
        assert path == "AI_TUTOR/CBSE/Class_12/Chemistry/Chemistry_Part_1"


# ---------------------------------------------------------------------------
# 4. clean_extracted_text(): Unicode normalization without altering language
# ---------------------------------------------------------------------------

class TestCleanExtractedText:
    def test_devanagari_text_passes_through_unchanged_visually(self):
        text = "विज्ञान"
        assert clean_extracted_text(text) == text

    def test_nfc_normalizes_equivalent_representations(self):
        # A precomposed form vs. its canonically-decomposed base+combining-mark
        # form must normalize to the identical string (NFC), even though both
        # render identically -- this is what makes two OCR passes of the
        # "same" printed text compare equal downstream.
        precomposed = unicodedata.normalize("NFC", "é")
        decomposed = unicodedata.normalize("NFD", "é")
        assert clean_extracted_text(decomposed) == precomposed

    def test_strips_zero_width_and_bom_characters(self):
        dirty = "\ufeffScience\u200b Chapter\u200e"
        cleaned = clean_extracted_text(dirty)
        assert "\ufeff" not in cleaned
        assert "\u200b" not in cleaned
        assert "\u200e" not in cleaned
        assert "Science" in cleaned and "Chapter" in cleaned

    def test_never_strips_zero_width_joiner_non_joiner_indic_control(self):
        """ZWJ/ZWNJ are meaningful, rendering-affecting characters in
        several Indic scripts -- they must NOT be treated as noise, unlike
        the lookup-key layer in compiler/normalization.py which strips
        them for internal matching purposes only."""
        text_with_zwnj = "क्\u200dष"
        assert "\u200d" in clean_extracted_text(text_with_zwnj)

    def test_idempotent(self):
        text = "क्षितिज"
        once = clean_extracted_text(text)
        twice = clean_extracted_text(once)
        assert once == twice

    def test_empty_and_none_safe(self):
        assert clean_extracted_text("") == ""
        assert clean_extracted_text(None) is None

    def test_never_raises_on_odd_input(self):
        # Defensive: must degrade gracefully, never crash chapter extraction.
        clean_extracted_text("\x00\x01 mixed \ud800 text")


# ---------------------------------------------------------------------------
# 5. LaTeX / escape-sequence normalization -- already-mature pipeline,
#    verified deterministic and non-book-specific (not modified by this
#    sprint; covered here so the sprint's own regression suite includes it)
# ---------------------------------------------------------------------------

class TestLatexAndEscapeNormalizationDeterministic:
    def test_colliding_latex_command_repaired_deterministically(self):
        raw = '{"eq": "\\frac{a}{b}"}'
        result1 = json_repair.repair_and_parse(raw)
        result2 = json_repair.repair_and_parse(raw)
        assert result1.success == result2.success
        if result1.success:
            assert result1.parsed == result2.parsed

    def test_smart_quotes_normalized(self):
        raw = "{\u201ckey\u201d: \u2018value\u2019}"
        result = json_repair.repair_and_parse(raw)
        assert result.success is True
        assert result.parsed == {"key": "value"}

    def test_unicode_math_symbol_normalization_available(self):
        assert hasattr(json_repair, "normalize_unicode_math_symbols")

    def test_repair_pipeline_never_raises_on_garbage(self):
        # Robustness contract: must never raise, regardless of book.
        result = json_repair.repair_and_parse("{{{{ not json at all @@@ ")
        assert result.success in (True, False)
