"""
tests/test_canonical_book_identity.py — regression tests for the Phase 1
Final Metadata Architecture Refinement.

Covers:
  1. parse_cover_metadata() -- generic subtitle/Part/Volume/edition
     extraction off synthetic cover-page Lines (no hardcoded subject).
  2. BookContext.educational_identity / derived_storage_identity /
     slug_source -- the three-tier identity model (canonical metadata,
     educational identity, derived storage identity) and its precedence.
  3. book_slug_source() -- the getattr-safe standalone equivalent.
  4. write_book_manifest() -- canonical metadata reaches the manifest
     without altering book_title.
  5. Backward compatibility -- books that already have an operator
     folder-name override, or that have no distinguishing cover metadata
     at all, keep producing the exact same storage identity as before
     this refinement.

Mirrors the existing test style in this suite: synthetic Line objects
(tests/test_pdf_parser_and_writer.py's `_line` helper) and a minimal fake
OneDriveStorage (tests/test_migration.py's FakeStorage pattern) -- no real
PDFs, no real network/MSAL calls.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.pdf_parser import (
    Line,
    BookContext,
    book_slug_source,
    parse_cover_metadata,
    parse_book_title_and_class,
    slugify,
)
from modules import json_writer
from storage.path_resolver import PathResolver


def _line(text, size=10.0, page=0, y=100.0, bold=False):
    return Line(text=text, size=size, max_size=size, bold=bold, font="Arial",
                page=page, y=y, page_height=800.0, bbox=(0, y, 100, y + size))


class _FakeOneDriveStorage:
    """Same minimal stand-in as test_pdf_parser_and_writer.py's own --
    only the methods json_writer.book_output_dir() actually calls."""

    def __init__(self):
        self._resolver = PathResolver()
        self.created_dirs = []
        self.uploaded = {}

    def resolve_path(self, board, klass, subject, book=None):
        return self._resolver.resolve(board, klass, subject, book)

    def create_directory(self, path):
        self.created_dirs.append(path)

    def upload_json(self, obj, path=None, indent=2, **kw):
        self.uploaded[path] = obj
        return path


# ---------------------------------------------------------------------------
# 1. parse_cover_metadata() -- generic extraction, no hardcoded subject
# ---------------------------------------------------------------------------

def test_parse_cover_metadata_extracts_subtitle():
    lines = [
        _line("Accountancy", size=24.0, y=50.0),
        _line("Partnership Accounts", size=18.0, y=90.0),
        _line("Textbook in Accountancy for Class XII", size=10.0, y=130.0),
    ]
    meta = parse_cover_metadata(lines, body_size=10.0, repeated=set(), book_title="Accountancy")
    assert meta["subtitle"] == "Partnership Accounts"
    assert meta["part"] is None
    assert meta["volume"] is None


def test_parse_cover_metadata_extracts_part_generically():
    # Deliberately a DIFFERENT subject than the Accountancy example above --
    # proves nothing here is keyed off a specific subject name.
    lines = [
        _line("Mathematics", size=24.0, y=50.0),
        _line("Part I", size=14.0, y=90.0),
        _line("Textbook in Mathematics for Class XII", size=10.0, y=130.0),
    ]
    meta = parse_cover_metadata(lines, body_size=10.0, repeated=set(), book_title="Mathematics")
    assert meta["part"] == "Part I"
    assert meta["subtitle"] is None


def test_parse_cover_metadata_extracts_volume():
    lines = [
        _line("Chemistry", size=24.0, y=50.0),
        _line("Volume 2", size=14.0, y=90.0),
    ]
    meta = parse_cover_metadata(lines, body_size=10.0, repeated=set(), book_title="Chemistry")
    assert meta["volume"] == "Volume 2"


def test_parse_cover_metadata_returns_all_none_when_nothing_distinguishing_present():
    # The common case: a single-part book with nothing but its title on
    # the cover.
    lines = [
        _line("Biology", size=24.0, y=50.0),
        _line("Textbook in Biology for Class XII", size=10.0, y=90.0),
    ]
    meta = parse_cover_metadata(lines, body_size=10.0, repeated=set(), book_title="Biology")
    assert meta == {"subtitle": None, "part": None, "volume": None, "edition": None}


def test_parse_cover_metadata_never_mutates_or_reads_back_book_title():
    lines = [
        _line("Physics", size=24.0, y=50.0),
        _line("Electrostatics", size=18.0, y=90.0),
    ]
    book_title, _, _ = parse_book_title_and_class(lines, body_size=10.0, repeated=set())
    meta = parse_cover_metadata(lines, body_size=10.0, repeated=set(), book_title=book_title)
    assert book_title == "Physics"
    assert meta["subtitle"] == "Electrostatics"


# ---------------------------------------------------------------------------
# 2. BookContext identity model -- educational_identity / derived_storage_
#    identity / slug_source precedence
# ---------------------------------------------------------------------------

def test_two_books_sharing_cover_title_get_unique_storage_identity():
    book1 = BookContext(book_title="Accountancy", cover_subtitle="Partnership Accounts")
    book2 = BookContext(book_title="Accountancy",
                         cover_subtitle="Company Accounts and Analysis of Financial Statements")

    assert book1.derived_storage_identity == "Accountancy - Partnership Accounts"
    assert book2.derived_storage_identity == \
        "Accountancy - Company Accounts and Analysis of Financial Statements"
    assert book1.derived_storage_identity != book2.derived_storage_identity
    # Canonical title itself is untouched and IS allowed to collide --
    # only the derived storage identity has to be unique.
    assert book1.book_title == book2.book_title == "Accountancy"


def test_educational_identity_prefers_subtitle_then_part_then_volume_then_title():
    assert BookContext(book_title="Accountancy", cover_subtitle="Partnership Accounts") \
        .educational_identity == "Partnership Accounts"
    assert BookContext(book_title="Mathematics", part="Part I").educational_identity == "Part I"
    assert BookContext(book_title="Chemistry", volume="Volume 2").educational_identity == "Volume 2"
    assert BookContext(book_title="Biology").educational_identity == "Biology"


def test_derived_storage_identity_is_deterministic():
    book = BookContext(book_title="Themes in Indian History", part="Part III")
    assert book.derived_storage_identity == book.derived_storage_identity == \
        "Themes in Indian History - Part III"


def test_derived_storage_identity_equals_book_title_when_no_distinguishing_metadata():
    book = BookContext(book_title="Biology")
    assert book.derived_storage_identity == "Biology"


def test_canonical_metadata_fields_stay_independently_preserved_not_concatenated():
    book = BookContext(book_title="Mathematics", part="Part I")
    # book_title is never rewritten to include "Part I".
    assert book.book_title == "Mathematics"
    assert book.part == "Part I"
    # Only the derived (storage-only) identity combines them.
    assert book.derived_storage_identity == "Mathematics - Part I"


# ---------------------------------------------------------------------------
# 3. slug_source / book_slug_source precedence + backward compatibility
# ---------------------------------------------------------------------------

def test_slug_source_prefers_folder_name_override_for_backward_compatibility():
    # A book already living under an operator-named folder must keep
    # producing that exact same path -- even though it now also has cover
    # metadata available.
    ctx = BookContext(book_title="Introductory to Macroeconomics")
    ctx.book_folder_name = "Class_11_Economics"
    ctx.cover_subtitle = "Some Subtitle That Must Not Win"
    assert ctx.slug_source == "Class_11_Economics"
    assert book_slug_source(ctx) == "Class_11_Economics"


def test_slug_source_uses_derived_storage_identity_when_no_folder_override():
    # This is the actual fix: no operator folder name is required any
    # more for two same-titled books to get unique, deterministic paths.
    ctx = BookContext(book_title="Accountancy", cover_subtitle="Partnership Accounts")
    assert ctx.book_folder_name is None
    assert ctx.slug_source == "Accountancy - Partnership Accounts"


def test_slug_source_falls_back_to_book_title_when_nothing_else_available():
    ctx = BookContext(book_title="Fundamentals of Physics")
    assert ctx.slug_source == "Fundamentals of Physics"


def test_book_slug_source_is_getattr_safe_for_pre_refinement_test_doubles():
    class _LegacyDouble:
        book_title = "Fundamentals of Physics"

    assert book_slug_source(_LegacyDouble()) == "Fundamentals of Physics"


def test_existing_books_without_subtitles_are_completely_unaffected():
    ctx = BookContext(book_title="Biology")
    assert ctx.cover_subtitle is None and ctx.part is None and ctx.volume is None
    assert ctx.educational_identity == "Biology"
    assert ctx.derived_storage_identity == "Biology"
    assert ctx.slug_source == "Biology"


# ---------------------------------------------------------------------------
# 4. OneDrive folder uniqueness end-to-end via PathResolver
# ---------------------------------------------------------------------------

def test_onedrive_folders_are_unique_for_same_titled_books():
    resolver = PathResolver()
    book1 = BookContext(book_title="Accountancy", cover_subtitle="Partnership Accounts")
    book2 = BookContext(book_title="Accountancy",
                         cover_subtitle="Company Accounts and Analysis of Financial Statements")

    path1 = resolver.resolve("CBSE", "12", "Accountancy", slugify(book1.slug_source))
    path2 = resolver.resolve("CBSE", "12", "Accountancy", slugify(book2.slug_source))

    assert path1 != path2
    assert path1 == "AI_TUTOR/CBSE/Class_12/Accountancy/Accountancy_Partnership_Accounts"
    assert path2 == ("AI_TUTOR/CBSE/Class_12/Accountancy/"
                      "Accountancy_Company_Accounts_And_Analysis_Of_Financial_Statements")


# ---------------------------------------------------------------------------
# 5. Book manifest carries canonical metadata without altering book_title
# ---------------------------------------------------------------------------

def test_write_book_manifest_preserves_canonical_metadata():
    storage = _FakeOneDriveStorage()
    json_writer.set_storage(storage)
    try:
        json_writer.write_book_manifest(
            klass="12", subject="Accountancy", book_slug="Accountancy_Partnership_Accounts",
            book_title="Accountancy", toc={"chapters": []},
            cover_subtitle="Partnership Accounts", part=None, volume=None, edition=None,
            educational_identity="Partnership Accounts",
            storage_identity="Accountancy - Partnership Accounts",
        )
    finally:
        json_writer.set_storage(None)

    manifest_path = [p for p in storage.uploaded if p.endswith("_book_manifest.json")][0]
    manifest = storage.uploaded[manifest_path]
    assert manifest["book_title"] == "Accountancy"
    assert manifest["book_subtitle"] == "Partnership Accounts"
    assert manifest["storage_identity"] == "Accountancy - Partnership Accounts"


def test_write_book_manifest_still_works_without_any_distinguishing_metadata():
    storage = _FakeOneDriveStorage()
    json_writer.set_storage(storage)
    try:
        json_writer.write_book_manifest(
            klass="12", subject="Biology", book_slug="Biology",
            book_title="Biology", toc={"chapters": []},
        )
    finally:
        json_writer.set_storage(None)

    manifest_path = [p for p in storage.uploaded if p.endswith("_book_manifest.json")][0]
    manifest = storage.uploaded[manifest_path]
    assert manifest["book_title"] == "Biology"
    assert manifest["book_subtitle"] is None
    assert manifest["storage_identity"] is None
