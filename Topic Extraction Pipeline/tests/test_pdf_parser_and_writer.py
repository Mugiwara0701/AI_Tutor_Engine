"""
tests/test_pdf_parser_and_writer.py — regression tests for three bugs fixed
in the output-directory / robustness pass on top of the frozen Phase-1
pipeline:

1. detect_chapter_title() could pick a bare decorative chapter-number
   ("1", "12", "IV", ...) instead of the real title, whenever that numeral
   happened to be set in a larger font than the title itself.
2. auto_detect_subject() picked the first KNOWN_SUBJECTS entry that
   appeared anywhere in the body text -- so a generic word like "science"
   used incidentally in a Business Studies chapter's prose ("management is
   a science...") would hijack the whole book's subject.
3. json_writer's output path used to get double-nested / mis-cased when
   combined with book_orchestrator's (now removed) per-book output_root
   layer: json_out/<book>/class_<klass>/<subject>/<book>/... instead of
   json_out/Class_<klass>/<Subject>/<Book_Name>/...

None of these touch the Chapter JSON schema itself.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.pdf_parser import Line, detect_chapter_title, auto_detect_subject, find_toc_lines
from modules import json_writer


def _line(text, size=10.0, page=0, y=100.0, bold=False):
    return Line(text=text, size=size, max_size=size, bold=bold, font="Arial",
                page=page, y=y, page_height=800.0, bbox=(0, y, 100, y + size))


# ---------------------------------------------------------------------------
# 1. chapter title must never be a bare numeral
# ---------------------------------------------------------------------------

def test_detect_chapter_title_ignores_bare_chapter_number():
    lines = [
        _line("1", size=48.0, y=50.0),   # big decorative chapter-number graphic
        _line("Nature and Significance of Management", size=22.0, y=120.0),
        _line("Management is essential for an organisation.", size=10.0, y=200.0),
    ]
    body_size = 10.0
    title = detect_chapter_title(lines, body_size, repeated=set())
    assert title == "Nature and Significance of Management"


def test_detect_chapter_title_still_works_without_a_numeral_present():
    lines = [
        _line("Introductory Macroeconomics", size=22.0, y=50.0),
        _line("This chapter introduces...", size=10.0, y=120.0),
    ]
    title = detect_chapter_title(lines, body_size=10.0, repeated=set())
    assert title == "Introductory Macroeconomics"


# ---------------------------------------------------------------------------
# 2. subject detection must prefer the most specific match, not the first
#    KNOWN_SUBJECTS entry that appears incidentally in the text
# ---------------------------------------------------------------------------

def test_auto_detect_subject_prefers_specific_subject_over_incidental_word():
    filename = "lebs101.pdf"
    first_page_text = ("Management is regarded both as an art and a science. "
                        "This chapter is part of the Business Studies syllabus.")
    subject = auto_detect_subject(filename, first_page_text)
    assert subject == "business studies"


def test_auto_detect_subject_falls_back_to_generic_word_when_thats_all_there_is():
    subject = auto_detect_subject("leph101.pdf", "This chapter covers topics in physical science.")
    assert subject == "science"


# ---------------------------------------------------------------------------
# 3. find_toc_lines should tolerate a "Contents" heading with trailing tokens
# ---------------------------------------------------------------------------

def test_find_toc_lines_tolerates_trailing_page_number():
    lines = [
        _line("Contents iii", page=0, y=50.0),
        _line("1. Nature and Significance of Management 1", page=0, y=80.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) == 1


def test_find_toc_lines_returns_empty_and_does_not_raise_when_absent():
    lines = [_line("Some unrelated front-matter line", page=0, y=50.0)]
    assert find_toc_lines(lines, repeated=set()) == []


# ---------------------------------------------------------------------------
# 4. output directory hierarchy: json_out/Class_<klass>/<Subject>/<Book>/...
#    with no duplicated/mis-ordered book-name segment
# ---------------------------------------------------------------------------

def test_chapter_output_path_builds_class_subject_book_hierarchy(tmp_path):
    out_path = json_writer.chapter_output_path(
        klass="12", subject="business studies", book_slug="business-studies-part-1",
        chapter_number=1, chapter_title="Nature and Significance of Management",
        output_root=str(tmp_path),
    )
    rel = os.path.relpath(out_path, str(tmp_path))
    parts = rel.split(os.sep)
    assert parts[0] == "Class_12"
    assert parts[1] == "Business_Studies"
    assert parts[2] == "Business_Studies_Part_1"
    assert parts[3] == "01_nature-and-significance-of-management.json"


def test_chapter_output_path_has_no_duplicated_book_segment(tmp_path):
    # Regression guard for the book_orchestrator + json_writer double-nesting
    # bug: the book name must appear exactly once in the resulting path.
    out_path = json_writer.chapter_output_path(
        klass="12", subject="science", book_slug="business",
        chapter_number=1, chapter_title="1",
        output_root=str(tmp_path),
    )
    rel = os.path.relpath(out_path, str(tmp_path))
    assert rel.lower().count("business") == 1
