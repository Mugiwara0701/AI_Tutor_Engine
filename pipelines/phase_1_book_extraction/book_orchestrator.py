"""
book_orchestrator.py — multi-book input discovery and orchestration layer.

This module sits ABOVE pipeline.py and does not touch chapter extraction,
the AI pipeline, or the Chapter JSON schema in any way. Its only job is to
figure out how many "books" are sitting under pdf_in/ and call pipeline.py's
existing, unmodified-in-substance process_all_pdfs() once per book:

    discover_books()
        -> for each book
            -> process_book(book)
                -> pipeline.process_all_pdfs(pdf_folder=book.pdf_folder, ...)
                    -> pipeline.process_chapter(...)   [existing, reused as-is]
                        -> existing extraction / OCR / VLM / json_writer

===========================================================================
INPUT LAYOUT (auto-detected, both work)
===========================================================================
    pdf_in/
    ├── Class_11_Economics/      <- a "book" folder: subfolder + *.pdf inside
    │   ├── lhat1ps.pdf
    │   └── lhat101.pdf
    ├── Class_10_Science/
    │   └── leec101.pdf
    └── lhat1ps.pdf              <- loose PDFs directly in pdf_in/ (legacy,
                                     backward-compatible: treated as ONE
                                     extra book with no name override, so it
                                     writes to json_out/ exactly like before)

===========================================================================
OUTPUT LAYOUT
===========================================================================
    json_out/
    └── Class_<klass>/
        └── <Subject>/
            └── <Book_Folder_Name>/
                ├── 01_....json
                ├── 02_....json
                └── _book_manifest.json

Every book -- named subfolder or legacy loose-PDF -- writes through the
same JSON_OUTPUT_FOLDER root (`output_root=None`); it's json_writer.py's
Class/Subject/Book nesting (see modules/json_writer.py's book_output_dir())
that actually separates books from each other, using the discovered
folder's *name* as the book identity (per the task spec, never inferred
from the PDFs) via `book_title_override`. Earlier this module used to also
prefix `output_root` with the book folder name, which duplicated the book
name and put it in the wrong position: json_out/<book>/class_<klass>/
<subject>/<book>/... instead of json_out/Class_<klass>/<subject>/<book>/...
"""
import os
import logging
from dataclasses import dataclass
from glob import glob
from typing import List, Optional, Callable

from config import PDF_INPUT_FOLDER, JSON_OUTPUT_FOLDER, STORAGE_BOARD
from modules import json_writer
from storage import OneDriveStorage
from storage.migration import ensure_migration_complete

logger = logging.getLogger("ncert_pipeline.orchestrator")


def _ensure_storage_ready() -> OneDriveStorage:
    """Startup gate, run once at the top of run() before any PDF
    extraction begins:

        Initialize Storage -> Authenticate -> check migration state
            -> if not complete: upload all existing local persistent
               data, verify uploads, mark migration complete
        -> only after that succeeds -> (run() goes on to) start PDF
           extraction

    Raises whatever storage/migration raise (AuthenticationError,
    MigrationError, ...) on failure; run() does not catch this, so a
    failed migration stops the whole startup before any book is
    discovered or processed, per the requirement that extraction must
    never begin before migration completes.
    """
    storage = OneDriveStorage()          # Initialize Storage
    storage.authenticate()               # Authenticate
    ensure_migration_complete(           # Check migration state / migrate / verify / mark complete
        storage, local_root=JSON_OUTPUT_FOLDER, board=STORAGE_BOARD
    )
    return storage


@dataclass
class Book:
    name: Optional[str]   # None for the legacy loose-PDF case; else the folder name
    pdf_folder: str
    # Always None: every book writes through the same JSON_OUTPUT_FOLDER
    # root. json_writer.py's own Class/Subject/Book_Name nesting (see
    # book_output_dir()) is what keeps different books' chapter JSONs
    # separated -- book.name reaches it via book_title_override, below.
    # (Previously this pointed at JSON_OUTPUT_FOLDER/<name>, which caused
    # json_writer to nest its own Class/Subject/Book folders *inside* that,
    # duplicating the book name and putting it in the wrong position.)
    output_root: Optional[str]

    @property
    def display_name(self) -> str:
        return self.name if self.name else "(pdf_in root — legacy flat layout)"


def _discover_books_under(dir_path: str, name_parts: List[str], books: List["Book"]) -> None:
    """Recursively finds every folder that directly contains *.pdf files
    and appends one Book per such folder, regardless of how many levels of
    subfolders sit above it. Covers both layouts with the same logic:

        pdf_in/Class_10_Science/*.pdf                  (1 level)
        pdf_in/Accountancy/Part 1/*.pdf                (2 levels)
        pdf_in/Accountancy/Part 2/*.pdf

    A folder becomes a Book the moment it directly holds PDFs -- a
    "Subject" folder that only has "Part N" children (no PDFs of its own)
    is never itself turned into a Book, only its Part subfolders are, so a
    two-level Subject/Part layout naturally produces one Book per Part
    without a Subject-level book also getting created alongside them.
    `name_parts` is the chain of folder names from the immediate child of
    pdf_in/ down to `dir_path`, joined with " - " for the Book's
    display/output name (e.g. "Accountancy - Part 1") so sibling Parts
    under the same Subject don't collide in json_out/.
    """
    subdirs = sorted(
        e for e in os.listdir(dir_path) if os.path.isdir(os.path.join(dir_path, e))
    )
    if glob(os.path.join(dir_path, "*.pdf")):
        books.append(Book(name=" - ".join(name_parts), pdf_folder=dir_path, output_root=None))
    elif not subdirs:
        logger.warning("Skipping '%s' — no PDFs found in this subfolder (and no further "
                        "subfolders to look in).", dir_path)

    for sub in subdirs:
        _discover_books_under(os.path.join(dir_path, sub), name_parts + [sub], books)


def discover_books(pdf_input_folder: Optional[str] = None) -> List[Book]:
    """Scans pdf_in/ (or `pdf_input_folder`) and returns one Book per
    folder that directly contains at least one *.pdf, searched at any
    depth under each top-level subfolder -- so both a flat
    "pdf_in/Subject/*.pdf" layout and a nested "pdf_in/Subject/Part N/
    *.pdf" layout (or deeper) are auto-detected the same way, with no
    separate code path for either. PLUS — for backward compatibility —
    one extra legacy Book if *.pdf files are also sitting directly inside
    pdf_in/ itself (the pre-multi-book behavior).

    Folders (at any depth) that contain neither PDFs nor further
    subfolders are ignored (nothing to process, no reason to fail the run
    over an empty/misplaced folder).
    """
    root = pdf_input_folder if pdf_input_folder is not None else PDF_INPUT_FOLDER
    books: List[Book] = []

    if not os.path.isdir(root):
        return books

    for entry in sorted(os.listdir(root)):
        entry_path = os.path.join(root, entry)
        if not os.path.isdir(entry_path):
            continue
        _discover_books_under(entry_path, [entry], books)

    # Backward compatibility: PDFs placed directly in pdf_in/ (old layout).
    if glob(os.path.join(root, "*.pdf")):
        books.append(Book(name=None, pdf_folder=root, output_root=None))

    return books


def process_book(book: Book, use_vlm: bool, page_batch_size: int, force: bool,
                  cancel_check: Optional[Callable[[], bool]] = None,
                  book_index: Optional[int] = None, total_books: Optional[int] = None) -> dict:
    """Runs the existing single-book pipeline over one discovered book
    folder. Never raises — a failed book is logged and reported so the
    caller can move on to the next one; a single bad book must not stop
    the rest of the run, same principle as the existing per-chapter
    error handling inside pipeline.process_all_pdfs().

    `cancel_check` (Phase F1, runtime/runtime.py): optional zero-arg
    callable, forwarded to pipeline.process_all_pdfs()'s own cancel_check
    (see that function's docstring). Passed as a keyword ONLY when not
    None, so callers/test doubles built against the pre-F1
    process_all_pdfs() signature (which doesn't accept cancel_check at
    all) keep working unchanged when this new parameter isn't used.
    `book_index` / `total_books`: optional, purely for the enriched
    per-chapter log block pipeline.process_chapter() prints (Book
    Progress: Book x/Total Books). Passed as keywords ONLY when not
    None, same test-double-safety convention as `cancel_check` above.
    """
    import pipeline  # local import: avoids a circular import at module load time

    print(f"\nBook:\n{book.display_name}\n")
    try:
        call_kwargs = dict(
            use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
            pdf_folder=book.pdf_folder, output_root=book.output_root,
            book_title_override=book.name,
        )
        if cancel_check is not None:
            call_kwargs["cancel_check"] = cancel_check
        if book_index is not None:
            call_kwargs["book_index"] = book_index
        if total_books is not None:
            call_kwargs["total_books"] = total_books
        stats = pipeline.process_all_pdfs(**call_kwargs)
        print(f"\n✓ Book Completed ({stats.get('written', 0)} written, "
              f"{stats.get('failed', 0)} failed, {stats.get('found', 0)} found)")
        return stats
    except Exception as e:
        logger.exception("Book '%s' failed entirely: %s", book.display_name, e)
        print(f"\n✗ Book FAILED: {e}")
        return {"found": 0, "written": 0, "failed": 0, "error": str(e)}


def run(use_vlm: bool = True, page_batch_size: int = 6, force: bool = False,
        pdf_input_folder: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """Top-level entry point: discover every book under pdf_in/, then
    process them one at a time, printing the console banners the task
    asked for. Returns the per-book stats dicts for anyone (tests, a
    caller script) that wants the numbers without scraping logs.

    `cancel_check` (Phase F1, runtime/runtime.py): optional zero-arg
    callable. Checked once before each book starts (stopping the
    remaining books here) and forwarded to process_book()/
    pipeline.process_all_pdfs() so it's also checked between chapters
    within the book currently running. Defaults to None -- when unset,
    this function's behavior is unchanged from before this parameter
    existed.

    `progress_callback` (Phase F1, runtime/runtime.py): optional
    one-arg callable invoked with that book's stats dict (the same dict
    appended to `all_stats`) immediately after each book finishes --
    book granularity, since that's the finest grain pipeline.py's
    existing return values expose without duplicating its internal
    per-chapter loop here. A callback that raises is logged and
    swallowed, never allowed to abort the run -- same "one failure
    must never stop the rest of the run" principle already applied to
    per-book/per-chapter errors elsewhere in this module. Defaults to
    None, in which case behavior is unchanged from before this
    parameter existed.
    """
    # Startup gate: storage init -> auth -> first-run migration must all
    # succeed BEFORE any PDF is discovered or extraction begins (see
    # _ensure_storage_ready()'s docstring for the exact required order).
    # Not wrapped in try/except here on purpose -- a migration failure
    # must stop startup entirely, not be swallowed like a per-book error.
    storage = _ensure_storage_ready()
    json_writer.set_storage(storage)

    books = discover_books(pdf_input_folder)

    print("=" * 50)
    print(f"Found {len(books)} book{'s' if len(books) != 1 else ''}.")
    print("=" * 50)

    if not books:
        logger.warning("No books found under '%s' (no subfolders with PDFs, and no loose PDFs either).",
                        os.path.abspath(pdf_input_folder or PDF_INPUT_FOLDER))
        return []

    all_stats = []
    n = len(books)
    for i, book in enumerate(books, start=1):
        if cancel_check is not None and cancel_check():
            logger.info("Cancellation requested; stopping before book %d/%d ('%s').",
                        i, n, book.display_name)
            break
        print(f"\nProcessing Book {i}/{n}")
        stats = process_book(book, use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
                              cancel_check=cancel_check, book_index=i, total_books=n)
        stats["book_name"] = book.display_name
        all_stats.append(stats)
        if progress_callback is not None:
            try:
                progress_callback(stats)
            except Exception:
                logger.exception("progress_callback raised for book '%s'; ignoring "
                                  "(a broken progress observer must never abort the run).",
                                  book.display_name)
        print("=" * 50)

    total_written = sum(s.get("written", 0) for s in all_stats)
    total_failed_chapters = sum(s.get("failed", 0) for s in all_stats)
    books_with_errors = sum(1 for s in all_stats if s.get("error"))
    logger.info("All books done. %d book(s) processed, %d chapter JSON(s) written, "
                "%d chapter failure(s), %d book-level failure(s).",
                n, total_written, total_failed_chapters, books_with_errors)
    return all_stats


if __name__ == "__main__":
    run()