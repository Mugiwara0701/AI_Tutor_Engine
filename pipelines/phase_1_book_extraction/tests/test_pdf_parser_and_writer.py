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
from modules.pdf_parser import (
    Line, detect_chapter_title, auto_detect_subject, find_toc_lines, parse_toc,
    match_chapter_in_toc,
)
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
# Milestone T3 -- chapter title / front-matter boundary detection.
#
# detect_chapter_title() used to search a hardcoded "page <= 1" window for
# the largest-font candidate. That's two separate root causes at once: (a)
# an in-body callout/subtopic heading appearing later on page 1 -- after
# real paragraph content has already started -- could still out-rank the
# real title just for being bigger/bolder, and (b) a title that genuinely
# starts past page 1 (an opening illustration on its own page, an epigraph
# on the next) was missed entirely, falling back to "untitled-chapter".
# Both are fixed by the same structural boundary: search only up to where
# real body prose begins, wherever that falls.
# ---------------------------------------------------------------------------

def test_detect_chapter_title_prefers_real_title_over_larger_in_body_callout():
    # The exact scenario from the roadmap: a chapter titled "Exception
    # Handling in Python" whose intro paragraph is followed, later in the
    # chapter, by a highlighted callout box ("Sorting") set in a bigger,
    # bolder font than the real title. The callout comes AFTER body prose
    # has already begun, so it must not be picked as the chapter title.
    lines = [
        _line("Exception Handling in Python", size=20.0, bold=True, page=0, y=40.0),
        _line("Errors are problems in a program due to which the program will stop "
              "the execution.", size=10.0, page=0, y=90.0),
        _line("On the other hand, exceptions are raised when some internal events "
              "occur.", size=10.0, page=0, y=110.0),
        _line("Sorting", size=24.0, bold=True, page=1, y=60.0),
        _line("Sorting is a common operation used throughout this chapter's "
              "examples.", size=10.0, page=1, y=90.0),
    ]
    title = detect_chapter_title(lines, body_size=10.0, repeated=set())
    assert title == "Exception Handling in Python"


def test_detect_chapter_title_finds_title_that_starts_past_page_one():
    # Front matter that runs longer than one page: a full-page opening
    # illustration credit on page 0, an epigraph on page 1, and the real
    # title only on page 2. Must not fall back to "untitled-chapter" just
    # because the title isn't within the first two pages.
    lines = [
        _line("Photograph courtesy NCERT archives", size=9.0, page=0, y=700.0),
        _line("\u201cThe only way to learn mathematics is to do mathematics.\u201d "
              "\u2014 Paul Halmos", size=11.0, page=1, y=300.0),
        _line("Real Numbers", size=22.0, bold=True, page=2, y=40.0),
        _line("In this chapter we revisit real numbers and their properties in "
              "detail.", size=10.0, page=2, y=90.0),
    ]
    title = detect_chapter_title(lines, body_size=10.0, repeated=set())
    assert title == "Real Numbers"


def test_detect_chapter_title_feeds_correct_toc_reconciliation():
    # End-to-end: a correctly detected title must be the thing that gets
    # fuzzy-matched against the TOC (match_chapter_in_toc) -- with the old
    # "Sorting" bug, this reconciliation step would either fail outright
    # or, worse, silently match the wrong chapter.
    lines = [
        _line("Exception Handling in Python", size=20.0, bold=True, page=0, y=40.0),
        _line("Errors are problems in a program due to which the program will stop "
              "the execution.", size=10.0, page=0, y=90.0),
        _line("Sorting", size=24.0, bold=True, page=1, y=60.0),
        _line("Sorting is a common operation used throughout this chapter's "
              "examples.", size=10.0, page=1, y=90.0),
    ]
    detected = detect_chapter_title(lines, body_size=10.0, repeated=set())
    toc = {"chapters": [
        {"number": 11, "title": "Sorting Algorithms", "page_start": 180, "topics": []},
        {"number": 12, "title": "Exception Handling in Python", "page_start": 200, "topics": []},
    ]}
    match = match_chapter_in_toc(detected, toc)
    assert match is not None
    assert match["title"] == "Exception Handling in Python"


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
# Milestone T1 — structural (keyword-independent) TOC page detection.
#
# _is_contents_heading only ever recognises one narrow English phrasing
# ("Contents" / "Table of Contents"); everything below exercises
# find_toc_lines on pages that either use a different heading word
# entirely (English "Index", Hindi, Sanskrit), no heading word at all, or
# different row typography/layout -- i.e. cases where the OLD
# keyword-only detector would have silently found nothing. Also covers
# the negative cases (decorative title pages, prose pages) that must
# NOT be misclassified as a TOC.
# ---------------------------------------------------------------------------

def test_find_toc_lines_detects_english_index_heading_via_structure():
    # "Index" is deliberately NOT one of the strings _is_contents_heading
    # recognises -- this page must still be found on row shape alone.
    lines = [
        _line("Index", page=0, y=40.0),
        _line("1. Real Numbers 1", page=0, y=70.0),
        _line("2. Polynomials 22", page=0, y=100.0),
        _line("3. Pair of Linear Equations 44", page=0, y=130.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) >= 3


def test_find_toc_lines_detects_hindi_toc_without_keyword_match():
    # "विषय सूची" is a real Hindi TOC heading, but _is_contents_heading has
    # no special-cased translation dictionary, so it is not recognised as
    # a keyword either -- detection here is 100% structural.
    lines = [
        _line("विषय सूची", page=0, y=40.0),
        _line("1. पर्यावरण अध्ययन 5", page=0, y=70.0),
        _line("2. जल संसाधन 18", page=0, y=100.0),
        _line("3. वन एवं वन्य जीवन 30", page=0, y=130.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) >= 3


def test_find_toc_lines_detects_sanskrit_toc_without_keyword_match():
    lines = [
        _line("अनुक्रमणिका", page=0, y=40.0),
        _line("1. संस्कृतभाषायाः परिचयः 3", page=0, y=70.0),
        _line("2. वर्णविचारः 12", page=0, y=100.0),
        _line("3. सन्धिः 25", page=0, y=130.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) >= 3


def test_find_toc_lines_detects_page_with_no_recognised_heading_word_at_all():
    # No heading line whatsoever -- not "Contents", not "Index", not any
    # language's equivalent. Sequential numbering + entry-row shape alone
    # must be enough.
    lines = [
        _line("1. Chapter A 1", page=0, y=40.0),
        _line("2. Chapter B 10", page=0, y=70.0),
        _line("3. Chapter C 20", page=0, y=100.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) == 3


def test_find_toc_lines_detects_dotted_leader_layout_without_chapter_numbers():
    # A different, common TOC layout: title + dotted leader + page number,
    # with no leading chapter-number token at all (so TOC_ENTRY_RE's
    # numbered-entry path never fires) -- must still be picked up via the
    # page-number-token/dotted-leader/alignment signals alone.
    lines = [
        _line("Introduction .......... 1", page=0, y=40.0),
        _line("Data Types .......... 15", page=0, y=70.0),
        _line("Control Structures .......... 30", page=0, y=100.0),
        _line("Functions .......... 45", page=0, y=130.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) == 4


def test_find_toc_lines_tolerates_typography_variation_across_entries():
    # Real books mix font sizes/weights across TOC rows (unit headers
    # bolder/larger than chapter rows, etc.) -- detection must not depend
    # on every row sharing identical typography.
    lines = [
        _line("Contents", size=18.0, bold=True, page=0, y=30.0),
        _line("1. Real Numbers 1", size=11.0, bold=False, page=0, y=60.0),
        _line("2. Polynomials 22", size=13.0, bold=True, page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", size=10.5, bold=False, page=0, y=120.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert len(toc_lines) >= 3


def test_find_toc_lines_does_not_classify_decorative_title_page_as_toc():
    # A cover/title page: large decorative text, no entry rows, no
    # page-number tokens, no sequential numbering.
    lines = [
        _line("MATHEMATICS", size=36.0, bold=True, page=0, y=200.0),
        _line("Textbook for Class X", size=18.0, page=0, y=260.0),
        _line("NCERT", size=14.0, page=0, y=320.0),
    ]
    assert find_toc_lines(lines, repeated=set()) == []


def test_find_toc_lines_does_not_classify_prose_page_as_toc():
    # Ordinary body-text page: no aligned page-number column, no dotted
    # leaders, no sequential chapter numbering.
    lines = [
        _line("Management is essential for any organisation to function.", page=0, y=40.0),
        _line("It coordinates the efforts of people towards common goals.", page=0, y=70.0),
        _line("This chapter introduces the basic concepts of management.", page=0, y=100.0),
    ]
    assert find_toc_lines(lines, repeated=set()) == []


def test_find_toc_lines_does_not_accept_heading_keyword_without_toc_structure():
    # A recognizable "Contents" heading followed by ordinary prose (no
    # entry rows, no page numbers, no numbering) must NOT be accepted --
    # the heading keyword is only ever a confidence booster on top of row
    # structure, never a substitute for it.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("This section describes how the book is organised for readers.", page=0, y=60.0),
        _line("It does not contain a list of chapters or page numbers.", page=0, y=90.0),
    ]
    assert find_toc_lines(lines, repeated=set()) == []


# ---------------------------------------------------------------------------
# Milestone T2 -- multi-page TOC extraction/merge.
#
# Real multi-page TOCs are broken across physical pages by a small
# non-entry artifact (a repeated running header, a stray footer page
# number, a unit/section divider) -- find_toc_lines's run-detection loop
# correctly stops at that artifact, but used to return the first page's
# entries immediately instead of checking whether more entries resume
# just past it. Everything below exercises that continuation/merge path.
# ---------------------------------------------------------------------------

def test_find_toc_lines_single_page_toc_is_unaffected_by_continuation_logic():
    # Baseline: a plain single-page TOC (no gap, nothing to continue past)
    # must still return exactly its own entries -- T2 must not change T1
    # behavior when there is nothing to merge.
    lines = [
        _line("Index", page=0, y=40.0),
        _line("1. Real Numbers 1", page=0, y=70.0),
        _line("2. Polynomials 22", page=0, y=100.0),
        _line("3. Pair of Linear Equations 44", page=0, y=130.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert [l.text for l in toc_lines] == [
        "1. Real Numbers 1", "2. Polynomials 22", "3. Pair of Linear Equations 44",
    ]


def test_find_toc_lines_merges_two_page_toc_across_running_header_break():
    # The reported bug, reproduced directly: chapters 1-3 on TOC page 1,
    # a repeated "Contents (Contd.)" running header at the top of TOC
    # page 2 (a very common NCERT layout), then chapters 4-5. All five
    # chapters must come back as one canonical, ordered list.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("1. Real Numbers 1", page=0, y=60.0),
        _line("2. Polynomials 22", page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", page=0, y=120.0),
        _line("Contents (Contd.)", page=1, y=20.0),
        _line("4. Quadratic Equations 73", page=1, y=50.0),
        _line("5. Arithmetic Progressions 99", page=1, y=80.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert [l.text for l in toc_lines] == [
        "1. Real Numbers 1", "2. Polynomials 22", "3. Pair of Linear Equations 44",
        "4. Quadratic Equations 73", "5. Arithmetic Progressions 99",
    ]


def test_find_toc_lines_merges_three_page_toc_across_mixed_gap_artifacts():
    # Three physical pages: a stray footer page number ("iv") ends page 1,
    # a unit divider ("UNIT III") interrupts page 2 -- neither is a TOC
    # entry, both are exactly the kind of page-break filler T2 must see
    # through. All seven chapters, across all three pages, must merge.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("1. Real Numbers 1", page=0, y=60.0),
        _line("2. Polynomials 22", page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", page=0, y=120.0),
        _line("iv", page=0, y=780.0),
        _line("4. Quadratic Equations 73", page=1, y=50.0),
        _line("5. Arithmetic Progressions 99", page=1, y=80.0),
        _line("UNIT III", page=1, y=110.0),
        _line("6. Triangles 122", page=2, y=40.0),
        _line("7. Coordinate Geometry 150", page=2, y=70.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert [l.text for l in toc_lines] == [
        "1. Real Numbers 1", "2. Polynomials 22", "3. Pair of Linear Equations 44",
        "4. Quadratic Equations 73", "5. Arithmetic Progressions 99",
        "6. Triangles 122", "7. Coordinate Geometry 150",
    ]


def test_find_toc_lines_continuation_detection_stops_at_real_prose():
    # A continuation search must never bridge into an unrelated section
    # (e.g. a Preface immediately following the TOC in the same prelims
    # file) just because its heading line is short/non-prose -- the
    # moment real sentence-shaped prose is hit with no entry row
    # resuming first, the search must give up and return only the TOC's
    # own entries.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("1. Real Numbers 1", page=0, y=60.0),
        _line("2. Polynomials 22", page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", page=0, y=120.0),
        _line("Preface", page=1, y=20.0),
        _line("This book has been written to help students understand mathematics.", page=1, y=50.0),
        _line("It follows the syllabus prescribed by the board of education.", page=1, y=80.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert [l.text for l in toc_lines] == [
        "1. Real Numbers 1", "2. Polynomials 22", "3. Pair of Linear Equations 44",
    ]


def test_find_toc_lines_merged_toc_preserves_printed_chapter_order():
    # End-to-end through parse_toc(): merged multi-page entries must
    # decode into chapter records in exactly the order they were
    # printed, with official number/title/page all intact.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("1. Real Numbers 1", page=0, y=60.0),
        _line("2. Polynomials 22", page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", page=0, y=120.0),
        _line("Contents (Contd.)", page=1, y=20.0),
        _line("4. Quadratic Equations 73", page=1, y=50.0),
        _line("5. Arithmetic Progressions 99", page=1, y=80.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    toc = parse_toc(toc_lines)
    assert [(c["number"], c["title"], c["page_start"]) for c in toc["chapters"]] == [
        (1, "Real Numbers", 1),
        (2, "Polynomials", 22),
        (3, "Pair of Linear Equations", 44),
        (4, "Quadratic Equations", 73),
        (5, "Arithmetic Progressions", 99),
    ]


def test_find_toc_lines_prevents_duplicate_entry_at_page_break_seam():
    # A page-break artifact that happens to restate the previous page's
    # last row verbatim (e.g. a "...continued from Chapter 3" style
    # repeat) must not produce a duplicate chapter entry in the merged
    # TOC.
    lines = [
        _line("Contents", page=0, y=30.0),
        _line("1. Real Numbers 1", page=0, y=60.0),
        _line("2. Polynomials 22", page=0, y=90.0),
        _line("3. Pair of Linear Equations 44", page=0, y=120.0),
        _line("Contents (Contd.)", page=1, y=20.0),
        _line("3. Pair of Linear Equations 44", page=1, y=40.0),
        _line("4. Quadratic Equations 73", page=1, y=70.0),
    ]
    toc_lines = find_toc_lines(lines, repeated=set())
    assert [l.text for l in toc_lines] == [
        "1. Real Numbers 1", "2. Polynomials 22", "3. Pair of Linear Equations 44",
        "4. Quadratic Equations 73",
    ]


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