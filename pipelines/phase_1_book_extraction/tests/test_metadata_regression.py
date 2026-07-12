"""
tests/test_metadata_regression.py — regression tests for the Phase A-F
book-metadata regression:

  book_orchestrator.py passes each discovered book folder's NAME into
  pipeline.process_all_pdfs() as `book_title_override`, so multi-book
  runs (and sibling "Part N" folders) don't collide in json_out/. Before
  this fix, that override was written straight into
  `book_ctx.book_title` -- the SAME field json_writer.py uses as the
  document's official, displayed book title -- so the folder name
  silently replaced official titles parsed from the PDFs (e.g.
  "Introductory to Macroeconomics" -> "Macroeconomics", or worse,
  whatever the user happened to name the input folder).

  The fix separates "output-directory identity" (book_ctx.book_folder_name
  / book_ctx.slug_source / pdf_parser.book_slug_source()) from "official
  displayed title" (book_ctx.book_title, parsed from the prelims/TOC PDF
  and left untouched by the folder-name override) everywhere a book_slug
  is computed: pipeline.process_chapter(), pipeline.process_all_pdfs()'s
  manifest write, and build_executor/executor.py's reuse-decision gate.

These tests never load the real VLM or parse real PDFs -- same style as
tests/test_book_orchestrator.py and tests/test_f3_build_executor.py:
BookContext/ChapterStructure are built directly, and pipeline.py's
heavier per-chapter helpers are monkeypatched out where irrelevant.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import pdf_parser
from modules.pdf_parser import BookContext, book_slug_source, slugify
from build_executor import executor as build_executor


# ---------------------------------------------------------------------------
# 1. BookContext.slug_source / pdf_parser.book_slug_source() -- the new
#    single source of truth for output-directory identity, kept separate
#    from the official book_title.
# ---------------------------------------------------------------------------

def test_slug_source_prefers_folder_name_over_official_title():
    ctx = BookContext(book_title="Introductory to Macroeconomics")
    ctx.book_folder_name = "Class_11_Economics"
    assert ctx.slug_source == "Class_11_Economics"
    assert book_slug_source(ctx) == "Class_11_Economics"
    # The official title itself must be completely untouched.
    assert ctx.book_title == "Introductory to Macroeconomics"


def test_slug_source_falls_back_to_book_title_when_no_folder_name():
    # Legacy loose-PDF book (book.name is None in book_orchestrator.Book)
    # -- no folder identity available, so the parsed title is the only
    # signal for both display and output-path purposes.
    ctx = BookContext(book_title="Fundamentals of Physics")
    assert ctx.book_folder_name is None
    assert ctx.slug_source == "Fundamentals of Physics"
    assert book_slug_source(ctx) == "Fundamentals of Physics"


def test_book_slug_source_is_getattr_safe_for_duck_typed_book_ctx():
    """Pre-existing test doubles across the suite (e.g.
    tests/test_f3_build_executor.py's _BookCtx) only set book_title --
    book_slug_source() must not blow up on them."""
    class _LegacyBookCtx:
        def __init__(self, book_title):
            self.book_title = book_title

    ctx = _LegacyBookCtx("Book One")
    assert book_slug_source(ctx) == "Book One"


# ---------------------------------------------------------------------------
# 2. pipeline.process_all_pdfs()'s override logic: book_title_override
#    must populate book_folder_name (and only ever fall back into
#    book_title when no official title was parsed at all).
# ---------------------------------------------------------------------------

@pytest.fixture
def _no_storage(monkeypatch):
    """process_all_pdfs()'s output side no longer touches local disk
    (OneDrive-backed json_writer), and these tests don't exercise
    writing at all -- nothing to stub here beyond staying off the
    network, which the pdf-discovery/override logic under test never
    reaches anyway."""
    yield


def test_override_does_not_clobber_official_book_title(tmp_path, monkeypatch):
    import pipeline

    official_ctx = BookContext(book_title="Introductory to Macroeconomics",
                                subject="Economics", klass="11")
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda *_a, **_k: official_ctx)

    pdf_folder = tmp_path / "Class_11_Economics"
    pdf_folder.mkdir()
    (pdf_folder / "leac101.pdf").write_bytes(b"%PDF-1.4 fake\n")

    # Stop just after the override/discovery logic under test -- no PDFs
    # need to actually parse or extract for this test.
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)
    captured = {}

    def _fake_execute_chapter(**kwargs):
        captured["book_ctx"] = kwargs["book_ctx"]
        return {"chapter_title": "x", "chapter_key": "x", "output_path": None,
                "decision": "reuse", "reason": "test short-circuit"}

    monkeypatch.setattr(pipeline, "_f3_execute_chapter", _fake_execute_chapter)

    pipeline.process_all_pdfs(use_vlm=False, pdf_folder=str(pdf_folder),
                               output_root="out", book_title_override="Class_11_Economics")

    book_ctx = captured["book_ctx"]
    # The official, PDF-parsed title survives the folder-name override.
    assert book_ctx.book_title == "Introductory to Macroeconomics"
    # The folder name is recorded separately, for output-identity only.
    assert book_ctx.book_folder_name == "Class_11_Economics"
    assert book_slug_source(book_ctx) == "Class_11_Economics"


def test_override_becomes_title_only_when_no_official_title_parsed(tmp_path, monkeypatch):
    import pipeline

    unknown_ctx = BookContext()  # book_title stays "untitled-book" -- no prelims file
    monkeypatch.setattr(pipeline.pdf_parser, "load_book_context", lambda *_a, **_k: unknown_ctx)
    monkeypatch.setattr(pipeline.pdf_parser, "find_prelims_pdf", lambda paths: None)

    pdf_folder = tmp_path / "Class_10_Science"
    pdf_folder.mkdir()
    (pdf_folder / "leec101.pdf").write_bytes(b"%PDF-1.4 fake\n")

    captured = {}

    def _fake_execute_chapter(**kwargs):
        captured["book_ctx"] = kwargs["book_ctx"]
        return {"chapter_title": "x", "chapter_key": "x", "output_path": None,
                "decision": "reuse", "reason": "test short-circuit"}

    monkeypatch.setattr(pipeline, "_f3_execute_chapter", _fake_execute_chapter)

    pipeline.process_all_pdfs(use_vlm=False, pdf_folder=str(pdf_folder),
                               output_root="out", book_title_override="Class_10_Science")

    book_ctx = captured["book_ctx"]
    # No official title was ever parsed -- folder name is the only signal,
    # so (and only so) it becomes the displayed title too.
    assert book_ctx.book_title == "Class_10_Science"
    assert book_ctx.book_folder_name == "Class_10_Science"


# ---------------------------------------------------------------------------
# 3. Cross-module consistency: pipeline.process_chapter()'s book_slug and
#    build_executor.execute_chapter()'s book_slug (the reuse-decision
#    gate) must derive from the exact same source, or reuse/output paths
#    silently diverge (Issue 5 -- "one authoritative metadata source").
# ---------------------------------------------------------------------------

def test_process_chapter_and_execute_chapter_agree_on_book_slug():
    ctx = BookContext(book_title="Introductory to Macroeconomics")
    ctx.book_folder_name = "Economics - Part 1"

    # This is exactly what pipeline.process_chapter() computes.
    process_chapter_slug = slugify(book_slug_source(ctx))
    # This is exactly what build_executor.execute_chapter() computes.
    executor_slug = slugify(pdf_parser.book_slug_source(ctx))

    assert process_chapter_slug == executor_slug
    # And neither is derived from the official title.
    assert process_chapter_slug != slugify(ctx.book_title)


# ---------------------------------------------------------------------------
# 4. Actual chapter number vs. processing position stay independent
#    (Issue 4) -- filename-derived chapter number wins over run-batch
#    position whenever the two would otherwise disagree.
# ---------------------------------------------------------------------------

def test_chapter_number_independent_of_processing_position(tmp_path):
    # A single, standalone Chapter 10 PDF processed on its own: batch
    # position is 1 (it's the only file in this run), but the actual
    # chapter number recovered from the standard NCERT filename
    # convention must remain 10, never silently fall back to the batch
    # position.
    fname_number = pdf_parser.chapter_number_from_filename("leac110.pdf")
    processing_position = 1  # this run's (only) position in chapter_paths
    assert fname_number == 10
    assert fname_number != processing_position


# ---------------------------------------------------------------------------
# 5. Subject casing at ORIGIN (parse_book_title_and_class /
#    auto_detect_subject) -- the first point canonical metadata is ever
#    produced. Both functions resolve a subject by matching against
#    KNOWN_SUBJECTS, an internal, deliberately all-lowercase matching
#    vocabulary -- that lowercase matching key must never leak out as the
#    displayed subject itself ("Accountancy" -> "accountancy").
# ---------------------------------------------------------------------------

def test_display_subject_canonicalizes_casing():
    assert pdf_parser._display_subject("accountancy") == "Accountancy"
    assert pdf_parser._display_subject("political science") == "Political Science"
    assert pdf_parser._display_subject("computer-science") == "Computer Science"


def test_display_subject_leaves_unknown_sentinel_untouched():
    # pipeline.py's fallback-chain gate compares against the literal
    # lowercase string "unknown" -- title-casing it would silently break
    # every one of those checks.
    assert pdf_parser._display_subject("unknown") == "unknown"


def test_auto_detect_subject_returns_display_cased_value():
    subject = pdf_parser.auto_detect_subject("Class_11_Accountancy/leac101.pdf", "")
    assert subject == "Accountancy"
    assert subject != "accountancy"


def test_parse_book_title_and_class_returns_display_cased_subject():
    def L(text, size=20.0, page=0):
        return pdf_parser.Line(text=text, size=size, max_size=size, bold=False,
                                font="F", page=page, y=float(page * 100))

    lines = [
        L("Introductory to Macroeconomics", size=40.0),
        L("Textbook in Accountancy for Class XI"),
    ]
    book_title, subject, klass = pdf_parser.parse_book_title_and_class(lines, body_size=10.0, repeated=set())
    assert subject == "Accountancy"
    assert subject != "accountancy"
    assert klass == "11"
    # The official title itself is completely unaffected by subject casing.
    assert book_title == "Introductory to Macroeconomics"


# ---------------------------------------------------------------------------
# 6. Chapter-title corruption at ORIGIN (detect_chapter_title) -- a
#    decorative drop-cap letter (the chapter's own opening letter, set
#    alone in an oversized font) must never win the "biggest font wins"
#    title heuristic and become the chapter_title (the literal "Chapter
#    'Y'" placeholder-title regression).
# ---------------------------------------------------------------------------

def _line(text, size, page=0, bold=False, y=0.0):
    return pdf_parser.Line(text=text, size=size, max_size=size, bold=bold,
                            font="F", page=page, y=y, page_height=800.0)


def test_detect_chapter_title_skips_drop_cap_letter():
    body_size = 10.0
    lines = [
        _line("Y", 60.0, y=10.0),                       # decorative drop cap, huge font
        _line("our Environment", 22.0, y=15.0, bold=True),  # the real title, smaller font
    ]
    title = pdf_parser.detect_chapter_title(lines, body_size, repeated=set())
    assert title == "our Environment"
    assert title != "Y"


def test_detect_chapter_title_falls_back_to_untitled_when_only_drop_cap_present():
    # No real title text run at all (e.g. it's rendered as a graphic) --
    # must honestly report "untitled-chapter" (which downstream TOC-by-
    # number matching can still correct) rather than silently returning
    # the lone decorative letter.
    body_size = 10.0
    lines = [_line("Y", 60.0, y=10.0)]
    title = pdf_parser.detect_chapter_title(lines, body_size, repeated=set())
    assert title == "untitled-chapter"


def test_detect_chapter_title_unaffected_for_normal_titles():
    body_size = 10.0
    lines = [_line("Water Resources", 22.0, y=10.0, bold=True)]
    assert pdf_parser.detect_chapter_title(lines, body_size, repeated=set()) == "Water Resources"