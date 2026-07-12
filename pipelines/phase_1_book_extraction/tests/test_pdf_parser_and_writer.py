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

TEST-INFRASTRUCTURE NOTE (bugfix, not a behavior change): the two
`test_chapter_output_path_*` tests below used to call
json_writer.chapter_output_path(..., output_root=str(tmp_path)) and then
inspect the local filesystem under `tmp_path`. That stopped matching
reality once json_writer.py's output moved entirely onto OneDrive (see
config.py: "JSON_OUTPUT_FOLDER ... it no longer names a local directory
that gets written to directly") -- book_output_dir() now always calls
through `storage.OneDriveStorage` (real network + real MSAL auth) even
when `output_root` is a plain local path string, and never uses
`output_root` to build a Class/Subject/Book hierarchy under it (see that
function's own docstring: "output_root ... is NOT a place to inject the
book name again"). So the old tests were silently making real Microsoft
Graph API calls with a Windows filesystem path as the "remote" path,
which fails outright off this project's network and is meaningless even
when it happens not to fail. Fixed here by injecting a lightweight fake
OneDriveStorage (mirrors tests/test_migration.py's own FakeStorage
pattern) via json_writer's existing set_storage() extension point, and
asserting on the returned OneDrive-relative path STRING instead of a
real filesystem path -- no production code's behavior changed, only how
these two tests observe it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from modules.pdf_parser import Line, detect_chapter_title, auto_detect_subject, find_toc_lines
from modules import json_writer
from storage.path_resolver import PathResolver


class _FakeOneDriveStorage:
    """Minimal stand-in for storage.OneDriveStorage, implementing only
    the two methods json_writer.book_output_dir() actually calls
    (resolve_path() / create_directory()) -- no MSAL/Graph/network
    involved. Reuses the real PathResolver (not a hand-rolled copy) so
    the exact Class_/Title_Case formatting this test asserts on is the
    same logic production code uses, not a duplicate guess at it."""

    def __init__(self):
        self._resolver = PathResolver()
        self.created_dirs = []

    def resolve_path(self, board, klass, subject, book=None):
        return self._resolver.resolve(board, klass, subject, book)

    def create_directory(self, path):
        self.created_dirs.append(path)


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
    # auto_detect_subject() returns canonically-cased display metadata
    # (see modules/pdf_parser.py's _display_subject() docstring for the
    # "Accountancy" -> "accountancy" regression this fixes) -- internal
    # matching against KNOWN_SUBJECTS still happens in lowercase.
    assert subject == "Business Studies"


def test_auto_detect_subject_falls_back_to_generic_word_when_thats_all_there_is():
    subject = auto_detect_subject("leph101.pdf", "This chapter covers topics in physical science.")
    assert subject == "Science"


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

def test_chapter_output_path_builds_class_subject_book_hierarchy(monkeypatch):
    monkeypatch.setattr(json_writer, "_storage_singleton", _FakeOneDriveStorage())
    out_path = json_writer.chapter_output_path(
        klass="12", subject="business studies", book_slug="business-studies-part-1",
        chapter_number=1, chapter_title="Nature and Significance of Management",
    )
    parts = out_path.split("/")
    assert parts[0] == "AI_TUTOR"
    assert parts[1] == config.STORAGE_BOARD
    assert parts[2] == "Class_12"
    assert parts[3] == "Business_Studies"
    assert parts[4] == "Business_Studies_Part_1"
    assert parts[5] == "json_out"
    assert parts[6] == "01_nature-and-significance-of-management.json"


def test_chapter_output_path_has_no_duplicated_book_segment(monkeypatch):
    # Regression guard for the book_orchestrator + json_writer double-nesting
    # bug: the book name must appear exactly once in the resulting path.
    monkeypatch.setattr(json_writer, "_storage_singleton", _FakeOneDriveStorage())
    out_path = json_writer.chapter_output_path(
        klass="12", subject="science", book_slug="business",
        chapter_number=1, chapter_title="1",
    )
    assert out_path.lower().count("business") == 1