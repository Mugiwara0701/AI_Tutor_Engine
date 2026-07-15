"""
tests/test_t4_chapter_numbering.py — regression tests for T4: resolving the
OFFICIAL printed chapter number independently of a chapter's local
position/index inside the current book or run.

Root cause covered here: modules.pdf_parser.parse_chapter_pdf() calls
match_chapter_by_position() as its second-line fallback (after
match_chapter_by_number(), before fuzzy title matching) whenever the
filename-derived chapter order doesn't resolve against the TOC. That
function was referenced (and extensively documented) throughout
pdf_parser.py but was never actually defined, so any chapter whose
filename-derived number fell through match_chapter_by_number() -- e.g. a
book with non-sequential local filenames -- crashed with an
AttributeError instead of falling back cleanly.

Only modules.pdf_parser is imported here (not modules.json_writer /
modules.validator) so these tests don't depend on the separate
`schemas`/`compiler` packages, which are unrelated to T4.
"""
from modules import pdf_parser


def _toc(pairs):
    """Build a minimal TOC dict: pairs of (printed_number, title)."""
    return {"chapters": [{"number": n, "title": t} for n, t in pairs]}


# ---------------------------------------------------------------------
# Single-volume books: local position == printed number. Must be unchanged.
# ---------------------------------------------------------------------
def test_single_volume_book_number_matches_position():
    toc = _toc([(1, "Intro"), (2, "Growth"), (3, "Markets")])
    match = pdf_parser.match_chapter_by_number(2, toc)
    assert match == {"number": 2, "title": "Growth"}


# ---------------------------------------------------------------------
# Part I / Part II continued-numbering books: the reported failure.
# Part II's own TOC prints 9, 10, ... even though its files locally
# restart at 01, 02, ...
# ---------------------------------------------------------------------
def test_part_two_continued_numbering_resolves_official_number():
    part_two_toc = _toc([(9, "Financial Management"), (10, "Financial Markets")])
    # Part II's first chapter PDF (local/filename-derived number == 1)
    match = pdf_parser.match_chapter_by_number(1, part_two_toc)
    assert match is not None
    assert match["number"] == 9  # official printed number, NOT local position 1
    assert match["title"] == "Financial Management"


# ---------------------------------------------------------------------
# Non-sequential local filenames: the filename-derived number doesn't
# land inside this book/part's own TOC at all. match_chapter_by_number()
# must return None (not raise), and match_chapter_by_position() must
# resolve it from this run's own processing order instead of crashing.
# ---------------------------------------------------------------------
def test_non_sequential_filename_falls_back_to_position_without_crashing():
    toc = _toc([(9, "Financial Management"), (10, "Financial Markets")])
    # filename-derived number (e.g. parsed from an oddly-named file) is
    # out of range for this TOC.
    assert pdf_parser.match_chapter_by_number(55, toc) is None
    # This file is nonetheless the 2nd one processed in this run.
    match = pdf_parser.match_chapter_by_position(2, toc)
    assert match == {"number": 10, "title": "Financial Markets"}


def test_match_chapter_by_position_out_of_range_returns_none():
    toc = _toc([(9, "Financial Management"), (10, "Financial Markets")])
    assert pdf_parser.match_chapter_by_position(0, toc) is None
    assert pdf_parser.match_chapter_by_position(3, toc) is None
    assert pdf_parser.match_chapter_by_position(None, toc) is None


def test_match_chapter_by_position_no_toc_returns_none():
    assert pdf_parser.match_chapter_by_position(1, None) is None
    assert pdf_parser.match_chapter_by_position(1, {"chapters": []}) is None


# ---------------------------------------------------------------------
# End-to-end fallback chain, replicating parse_chapter_pdf()'s own T4
# resolution order: by_number -> by_position -> fuzzy title match.
# ---------------------------------------------------------------------
def test_full_fallback_chain_never_raises_and_prefers_number_over_position():
    toc = _toc([(9, "Financial Management"), (10, "Financial Markets")])

    def resolve(chapter_order_fallback, processing_position, chapter_title=""):
        toc_match = pdf_parser.match_chapter_by_number(chapter_order_fallback, toc)
        if not toc_match:
            toc_match = pdf_parser.match_chapter_by_position(processing_position, toc)
        if not toc_match:
            toc_match = pdf_parser.match_chapter_in_toc(chapter_title, toc)
        return toc_match

    # Good filename-derived number: resolved by value, position ignored.
    assert resolve(1, 1)["number"] == 9
    # Bad/non-sequential filename-derived number: falls back to position.
    assert resolve(55, 2)["number"] == 10
