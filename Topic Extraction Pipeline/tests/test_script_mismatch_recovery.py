"""
tests/test_script_mismatch_recovery.py — verifies the fix for the
legacy-font ("Kruti Dev"-style) Hindi/Sanskrit symptom described in
modules/language_detector.py: a script-mismatched text layer produces
garbled chapter_title/heading text that previously went straight into the
Chapter JSON uncorrected, because the recover_chapter_title / recover_heading
VLM tasks existed in prompt_manager but were never called anywhere.

Two layers, matching tests/test_semantic_processor.py's existing style:
  - semantic_processor.process_recover_chapter_title / process_recover_heading:
    thin wrappers around _run_task, exercised with a FakeAdapter (no GPU).
  - pipeline._recover_script_mismatched_text: the orchestration that decides
    *when* to call those wrappers (script-ratio mismatch) and mutates
    structure.chapter_title / structure.topics[].title in place.

Run: python -m pytest tests/test_script_mismatch_recovery.py -v
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import fitz

import pipeline
from modules import semantic_processor
from modules.pdf_parser import ChapterStructure, TopicRecord
from prompt_manager.model_adapter import ModelAdapter, AdapterResponse
from prompt_manager.prompt_manager import PromptManager

# A real Hindi chapter title, and the kind of Latin-looking gibberish a
# legacy Kruti-Dev-style font produces for the exact same glyphs when
# PyMuPDF reads the underlying (mismapped) code points instead of the
# rendered glyphs.
REAL_HINDI_TITLE = "राष्ट्रीय आय का लेखांकन"
GARBLED_TITLE = "jkVªh; vk; dk ys[kkadu"

REAL_HINDI_HEADING = "मुद्रा और बैंकिंग"
GARBLED_HEADING = "eqnzk vkSj cSafdax"


@pytest.fixture
def blank_doc():
    doc = fitz.open()
    doc.new_page(width=400, height=600)
    doc.new_page(width=400, height=600)
    yield doc
    doc.close()


def make_structure(**overrides):
    defaults = dict(
        filename="ch1.pdf", subject="economics", klass="class_12",
        chapter_title=GARBLED_TITLE, chapter_number=1, toc_matched=False,
        num_pages=2, lines=[], body_size=10.5, repeated=set(),
        topics=[], page_word_counts={}, page_sizes={}, language="hi",
    )
    defaults.update(overrides)
    structure = ChapterStructure(**defaults)
    structure.book_title = "अर्थशास्त्र"  # attached dynamically, same as pipeline.py does
    return structure


def make_topic(**overrides):
    defaults = dict(
        id="t1", title=GARBLED_HEADING, numbering="1.1", level=1, parent=None,
        page_start=0, page_end=0, bbox=(10, 10, 200, 200), reading_order=0,
        body_text="", confidence=0.6, signals={},
    )
    defaults.update(overrides)
    return TopicRecord(**defaults)


class FakeAdapter(ModelAdapter):
    """Same pattern as tests/test_semantic_processor.py's FakeAdapter."""
    adapter_id = "fake-adapter-for-recovery-tests"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, prompt, images=None, max_new_tokens=None):
        self.calls.append({"prompt": prompt, "images": images})
        if not self._responses:
            raise RuntimeError("FakeAdapter ran out of canned responses")
        return self._responses.pop(0)

    def generate_json(self, prompt, images=None, max_new_tokens=None):
        raw = self.generate(prompt, images=images, max_new_tokens=max_new_tokens)
        try:
            return AdapterResponse(success=True, raw_output=raw, cleaned_output=raw,
                                    parsed_output=json.loads(raw))
        except Exception:
            return AdapterResponse(success=False, raw_output=raw, cleaned_output=raw,
                                    parsed_output=None, error_message="not valid JSON")


def _use_fake_manager(monkeypatch, responses):
    manager = PromptManager(FakeAdapter(responses))
    monkeypatch.setattr(semantic_processor, "_get_prompt_manager", lambda: manager)
    return manager


TRIPLE = lambda v, c=0.85, e="matches rendered glyphs in page image": {
    "value": v, "confidence": c, "evidence_basis": e}


# ---------------------------------------------------------------------------
# semantic_processor.process_recover_chapter_title / process_recover_heading
# ---------------------------------------------------------------------------
def test_process_recover_chapter_title_returns_flat_dict(monkeypatch, blank_doc):
    response = json.dumps({"chapter_title": TRIPLE(REAL_HINDI_TITLE)})
    manager = _use_fake_manager(monkeypatch, [response])

    result = semantic_processor.process_recover_chapter_title(
        blank_doc, 0, GARBLED_TITLE, "अर्थशास्त्र", "economics", "some ocr text")

    assert result["chapter_title"] == REAL_HINDI_TITLE
    # An image must actually be sent -- this is a vision task, not text-only.
    assert len(manager.adapter.calls[0]["images"]) == 1


def test_process_recover_chapter_title_clamps_out_of_range_page_hint(monkeypatch, blank_doc):
    """blank_doc only has 2 pages (indices 0-1); a page_hint of 99 must not
    raise, it should clamp to the last real page."""
    response = json.dumps({"chapter_title": TRIPLE(REAL_HINDI_TITLE)})
    _use_fake_manager(monkeypatch, [response])

    result = semantic_processor.process_recover_chapter_title(
        blank_doc, 99, GARBLED_TITLE, "अर्थशास्त्र", "economics", "some ocr text")

    assert result["chapter_title"] == REAL_HINDI_TITLE


def test_process_recover_heading_returns_title_and_numbering(monkeypatch, blank_doc):
    response = json.dumps({
        "heading_title": TRIPLE(REAL_HINDI_HEADING),
        "numbering": TRIPLE("3.3"),
    })
    manager = _use_fake_manager(monkeypatch, [response])

    result = semantic_processor.process_recover_heading(
        blank_doc, 0, (10, 10, 200, 200), 1, "ocr region text", [], REAL_HINDI_TITLE)

    assert result["heading_title"] == REAL_HINDI_HEADING
    assert result["numbering"] == "3.3"
    assert len(manager.adapter.calls[0]["images"]) == 1


def test_recovery_failure_preserves_raw_output(monkeypatch, blank_doc):
    """Malformed model output should degrade gracefully (never raise), but
    per the JSON-repair-layer fix (ISSUE 2) it must no longer collapse to a
    bare {} -- that used to discard the model's raw text the moment JSON
    parsing/validation failed, indistinguishable from "nothing came back at
    all". The contract now is: no recognized fields (so callers' normal
    `.get(key, default)` still behaves exactly as before), but the raw
    output and validation errors are preserved for audit/reprocessing.
    PromptManager does one internal retry, so two bad responses are needed
    to exhaust it."""
    _use_fake_manager(monkeypatch, ["not valid json", "still not valid json"])

    result = semantic_processor.process_recover_chapter_title(
        blank_doc, 0, GARBLED_TITLE, "अर्थशास्त्र", "economics", "some ocr text")

    assert result.get("chapter_title") is None
    assert result["_vlm_failed"] is True
    assert result["_vlm_raw_output"] == "still not valid json"


# ---------------------------------------------------------------------------
# pipeline._recover_script_mismatched_text — the orchestration layer
# ---------------------------------------------------------------------------
def test_garbled_chapter_title_gets_recovered(monkeypatch, blank_doc):
    structure = make_structure(chapter_title=GARBLED_TITLE, language="hi")
    response = json.dumps({"chapter_title": TRIPLE(REAL_HINDI_TITLE)})
    _use_fake_manager(monkeypatch, [response])
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "ocr text", 1: ""}, logs)

    assert structure.chapter_title == REAL_HINDI_TITLE
    assert any("recovered via VLM" in w for w in logs["warnings"])


def test_already_correct_devanagari_title_is_left_alone(monkeypatch, blank_doc):
    """If the text layer is fine (real Unicode Devanagari already), no VLM
    call should happen at all -- recovery is a targeted fallback, not a
    blanket re-verification of every chapter."""
    structure = make_structure(chapter_title=REAL_HINDI_TITLE, language="hi")
    manager = _use_fake_manager(monkeypatch, [])  # no canned responses -- would raise if called
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "ocr text", 1: ""}, logs)

    assert structure.chapter_title == REAL_HINDI_TITLE
    assert manager.adapter.calls == []


def test_english_book_is_never_sent_through_recovery(monkeypatch, blank_doc):
    """An English chapter title made of Latin letters always matches the
    'en' script range, so this should never fire for the common case."""
    structure = make_structure(chapter_title="National Income Accounting", language="en")
    manager = _use_fake_manager(monkeypatch, [])
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "", 1: ""}, logs)

    assert structure.chapter_title == "National Income Accounting"
    assert manager.adapter.calls == []


def test_garbled_heading_gets_recovered_and_id_untouched(monkeypatch, blank_doc):
    topic = make_topic(title=GARBLED_HEADING, numbering="1.1")
    structure = make_structure(chapter_title=REAL_HINDI_TITLE, topics=[topic], language="hi")
    response = json.dumps({
        "heading_title": TRIPLE(REAL_HINDI_HEADING),
        "numbering": TRIPLE("1.1"),
    })
    _use_fake_manager(monkeypatch, [response])
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "ocr text", 1: ""}, logs)

    assert structure.topics[0].title == REAL_HINDI_HEADING
    assert structure.topics[0].id == "t1"  # internal id is unaffected by the text fix
    assert any("heading on page 0 recovered via VLM" in w for w in logs["warnings"])


def test_recovery_miss_keeps_original_and_logs_it(monkeypatch, blank_doc):
    """If the VLM also fails to produce usable script (e.g. OCR pack missing
    and it guesses in English), keep the original text rather than writing
    something worse, but make the miss visible in extraction_logs."""
    structure = make_structure(chapter_title=GARBLED_TITLE, language="hi")
    response = json.dumps({"chapter_title": TRIPLE("National Income Accounting")})  # wrong script
    _use_fake_manager(monkeypatch, [response])
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "ocr text", 1: ""}, logs)

    assert structure.chapter_title == GARBLED_TITLE  # unchanged
    assert any("did not return usable text" in w for w in logs["warnings"])


def test_untitled_chapter_placeholder_is_not_sent_to_recovery(monkeypatch, blank_doc):
    """'untitled-chapter' is pdf_parser's own explicit 'nothing detected'
    sentinel, not a script-mismatch symptom -- recovering a title guess out
    of thin air (no candidate at all) is out of scope for this fix."""
    structure = make_structure(chapter_title="untitled-chapter", language="hi")
    manager = _use_fake_manager(monkeypatch, [])
    logs = {"warnings": []}

    pipeline._recover_script_mismatched_text(blank_doc, structure, {0: "", 1: ""}, logs)

    assert structure.chapter_title == "untitled-chapter"
    assert manager.adapter.calls == []
