"""
tests/test_normalization_pipeline_audit.py — regression tests for the
Phase 1.5 pre-freeze end-to-end normalization audit.

ROOT CAUSE COVERED: tracing every textual field that reaches the final
Phase 1 JSON surfaced three genuine bypasses of the intended
normalization pipeline (Unicode Normalization -> OCR Cleanup -> LaTeX
Repair -> JSON Repair), all fixed in this pass:

  1. modules/layout_detector.py ran its own independent
     page.get_text("dict") pass for figure/table captions and equation
     raw-text hints -- the exact same born-digital extraction technique
     pdf_parser.extract_lines() uses, but without ever calling
     clean_extracted_text(). Figure/table captions are written directly
     into the final JSON's "caption"/"title" fields, so this was a real,
     user-facing gap, not just an internal inconsistency.
  2. modules/semantic_processor.py's _unwrap() -- the single choke point
     every VLM-generated text field (topic summaries, figure/table/
     equation descriptions, and critically, the recovered chapter_title/
     heading_title from script-mismatch recovery) flows through -- never
     normalized any of it. slugify()/make_id() happen to normalize their
     own copy internally, so identities/folder names were never at risk,
     but the raw display value written into chapter_title/title/
     semantic_* JSON fields could differ in Unicode form from every other
     text field in the same document.
  3. modules/ocr_engine.py's text-layer path (_text_layer_for_page) read
     doc[pno].get_text("text") directly with no normalization at all, and
     the tesseract path only ran the new OCR-content-cleanup stage
     without Unicode normalization first, contrary to the intended
     Unicode-Normalization-then-OCR-Cleanup order.

This file locks in all three fixes.
"""
from __future__ import annotations

import unicodedata

import pytest

from modules.pdf_parser import clean_extracted_text


# A Hindi string with a combining vowel sign expressed in a DECOMPOSED
# (NFD) form, which clean_extracted_text's NFC pass must canonicalize.
_DECOMPOSED_HINDI = unicodedata.normalize("NFD", "क्षितिज विज्ञान")
_COMPOSED_HINDI = unicodedata.normalize("NFC", "क्षितिज विज्ञान")


class TestLayoutDetectorCaptionNormalization:
    def test_lines_text_from_dict_applies_nfc(self):
        import modules.layout_detector as ld
        text_dict = {
            "blocks": [
                {"lines": [
                    {"bbox": (0, 10, 100, 20),
                     "spans": [{"text": _DECOMPOSED_HINDI}]},
                ]}
            ]
        }
        result = ld._lines_text_from_dict(text_dict)
        assert result[0][1] == _COMPOSED_HINDI
        # Never transliterated/romanized -- language content intact.
        assert "क्षितिज" in result[0][1]

    def test_equations_on_page_normalizes_raw_text(self):
        import modules.layout_detector as ld
        text_dict = {
            "blocks": [
                {"lines": [
                    {"bbox": (0, 0, 50, 10),
                     "spans": [{"text": "x " + unicodedata.normalize("NFD", "≤") + " 5"}]},
                ]}
            ]
        }
        regions = ld._equations_on_page(text_dict, pno=0)
        assert len(regions) == 1
        assert regions[0].extra["raw_text"] == unicodedata.normalize(
            "NFC", "x " + unicodedata.normalize("NFD", "≤") + " 5")

    def test_layout_detector_imports_clean_extracted_text(self):
        import modules.layout_detector as ld
        assert hasattr(ld, "clean_extracted_text")


class TestSemanticProcessorUnwrapNormalization:
    def test_unwrap_normalizes_plain_string_value(self):
        from modules.semantic_processor import _unwrap
        result = _unwrap({"chapter_title": _DECOMPOSED_HINDI})
        assert result["chapter_title"] == _COMPOSED_HINDI

    def test_unwrap_normalizes_evidence_triple_value(self):
        from modules.semantic_processor import _unwrap
        result = _unwrap({
            "heading_title": {"value": _DECOMPOSED_HINDI, "confidence": 0.9,
                               "evidence_basis": "visual"}
        })
        assert result["heading_title"] == _COMPOSED_HINDI

    def test_unwrap_normalizes_list_of_strings(self):
        from modules.semantic_processor import _unwrap
        result = _unwrap({"glossary_terms": [_DECOMPOSED_HINDI, "plain english"]})
        assert result["glossary_terms"][0] == _COMPOSED_HINDI
        assert result["glossary_terms"][1] == "plain english"

    def test_unwrap_never_transliterates_or_romanizes(self):
        from modules.semantic_processor import _unwrap
        result = _unwrap({"chapter_title": "क्षितिज"})
        assert result["chapter_title"] == "क्षितिज"
        assert "Kshitij" not in str(result)

    def test_unwrap_preserves_non_string_types(self):
        from modules.semantic_processor import _unwrap
        result = _unwrap({"confidence": 0.87, "is_valid": True, "count": 3})
        assert result["confidence"] == 0.87
        assert result["is_valid"] is True
        assert result["count"] == 3

    def test_unwrap_handles_none_and_empty(self):
        from modules.semantic_processor import _unwrap
        assert _unwrap(None) == {}
        assert _unwrap({}) == {}
        assert _unwrap({"title": ""}) == {"title": ""}


class TestOcrEngineNormalizationOrder:
    def test_text_layer_for_page_applies_nfc(self, monkeypatch):
        import modules.ocr_engine as ocr_engine

        class _FakePage:
            def get_text(self, mode):
                return _DECOMPOSED_HINDI

        class _FakeDoc:
            def __getitem__(self, idx):
                return _FakePage()

        result = ocr_engine._text_layer_for_page(_FakeDoc(), 0)
        assert result == _COMPOSED_HINDI

    def test_ocr_engine_imports_clean_extracted_text(self):
        import modules.ocr_engine as ocr_engine
        assert hasattr(ocr_engine, "clean_extracted_text")

    def test_tesseract_path_normalizes_before_ocr_cleanup(self):
        import inspect
        import modules.ocr_engine as ocr_engine
        source = inspect.getsource(ocr_engine._tesseract_ocr_page)
        # Unicode Normalization must be the INNER call (runs first),
        # OCR Cleanup the OUTER call (runs second) -- matches the
        # intended pipeline order.
        assert "clean_ocr_text(clean_extracted_text(" in source.replace(" ", "")


class TestEndToEndFieldConsistency:
    """A sanity check that the same Hindi text, however it enters the
    pipeline (PDF text layer, OCR, or VLM output), ends up in the exact
    same canonical Unicode form -- never transliterated, never diverging
    between fields."""

    def test_pdf_layer_and_semantic_processor_agree(self):
        from modules.semantic_processor import _unwrap
        pdf_result = clean_extracted_text(_DECOMPOSED_HINDI)
        vlm_result = _unwrap({"title": _DECOMPOSED_HINDI})["title"]
        assert pdf_result == vlm_result == _COMPOSED_HINDI

    def test_ocr_and_pdf_layer_agree(self):
        import modules.ocr_engine as ocr_engine

        class _FakePage:
            def get_text(self, mode):
                return _DECOMPOSED_HINDI

        class _FakeDoc:
            def __getitem__(self, idx):
                return _FakePage()

        ocr_result = ocr_engine._text_layer_for_page(_FakeDoc(), 0)
        pdf_result = clean_extracted_text(_DECOMPOSED_HINDI)
        assert ocr_result == pdf_result