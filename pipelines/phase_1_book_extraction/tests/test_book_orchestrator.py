"""
tests/test_book_orchestrator.py — unit/integration tests for the new
multi-book discovery/orchestration layer (book_orchestrator.py) added on
top of the frozen Phase-1 pipeline.

These tests never load the real VLM or parse real PDFs: pipeline.process_all_pdfs
is monkeypatched to a stub that records how it was called and returns a
stats dict, so we're testing ORCHESTRATION (discovery, looping, per-book
error isolation, backward compatibility) in isolation from extraction.
"""
import os
import sys
import importlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_orchestrator  # noqa: E402


def _touch_pdf(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4 fake\n")


# ---------------------------------------------------------------------------
# discover_books()
# ---------------------------------------------------------------------------

def test_discover_books_multi_book_layout(tmp_path):
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "Class_11_Economics" / "lhat101.pdf"))
    _touch_pdf(str(pdf_in / "Class_11_Economics" / "lhat102.pdf"))
    _touch_pdf(str(pdf_in / "Class_10_Science" / "leec101.pdf"))

    books = book_orchestrator.discover_books(str(pdf_in))

    names = sorted(b.name for b in books)
    assert names == ["Class_10_Science", "Class_11_Economics"]
    for b in books:
        # output_root stays None for every book -- json_writer.py's own
        # Class/Subject/Book_Name nesting (fed by book_title_override, not
        # output_root) is what separates books' output.
        assert b.output_root is None
        assert os.path.isdir(b.pdf_folder)


def test_discover_books_backward_compatible_flat_layout(tmp_path):
    """Old-style layout: PDFs sitting directly in pdf_in/, no subfolders."""
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "lhat1ps.pdf"))
    _touch_pdf(str(pdf_in / "lhat101.pdf"))

    books = book_orchestrator.discover_books(str(pdf_in))

    assert len(books) == 1
    assert books[0].name is None
    assert books[0].output_root is None  # falls back to JSON_OUTPUT_FOLDER inside pipeline.py
    assert books[0].pdf_folder == str(pdf_in)


def test_discover_books_mixed_layout_processes_both(tmp_path):
    """Subfolders AND loose PDFs present at once: both should be discovered
    (subfolder books first, then the legacy loose-PDF book), so migrating
    gradually to the new layout doesn't silently drop any book."""
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "Class_12_Biology" / "bio01.pdf"))
    _touch_pdf(str(pdf_in / "legacy_loose.pdf"))

    books = book_orchestrator.discover_books(str(pdf_in))

    assert len(books) == 2
    assert books[0].name == "Class_12_Biology"
    assert books[1].name is None


def test_discover_books_ignores_empty_subfolders(tmp_path):
    pdf_in = tmp_path / "pdf_in"
    os.makedirs(str(pdf_in / "Empty_Folder"))
    _touch_pdf(str(pdf_in / "Has_Pdfs" / "a.pdf"))

    books = book_orchestrator.discover_books(str(pdf_in))

    assert [b.name for b in books] == ["Has_Pdfs"]


def test_discover_books_missing_root_returns_empty(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert book_orchestrator.discover_books(str(missing)) == []


def test_discover_books_no_pdfs_anywhere_returns_empty(tmp_path):
    pdf_in = tmp_path / "pdf_in"
    os.makedirs(str(pdf_in))
    assert book_orchestrator.discover_books(str(pdf_in)) == []


# ---------------------------------------------------------------------------
# process_book() / run() — orchestration + error isolation, extraction mocked
# ---------------------------------------------------------------------------

class _FakePipeline:
    """Stand-in for the real pipeline module. Records every call so tests
    can assert on how process_all_pdfs was invoked, and can be told to
    raise for a specific book folder to exercise book-level error
    isolation."""
    def __init__(self, raise_for_folder=None):
        self.calls = []
        self.raise_for_folder = raise_for_folder

    def process_all_pdfs(self, use_vlm, page_batch_size, force, pdf_folder=None,
                          output_root=None, book_title_override=None):
        self.calls.append(dict(use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
                                pdf_folder=pdf_folder, output_root=output_root,
                                book_title_override=book_title_override))
        if self.raise_for_folder and pdf_folder == self.raise_for_folder:
            raise RuntimeError("simulated catastrophic book failure")
        return {"found": 2, "written": 2, "failed": 0, "book_title": book_title_override or "untitled-book"}


@pytest.fixture
def fake_pipeline(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setitem(sys.modules, "pipeline", fake)
    return fake


def test_process_book_calls_pipeline_with_folder_name_as_book_title(fake_pipeline):
    book = book_orchestrator.Book(name="Class_11_Economics", pdf_folder="/pdf_in/Class_11_Economics",
                                   output_root=None)

    stats = book_orchestrator.process_book(book, use_vlm=False, page_batch_size=6, force=False)

    assert stats["written"] == 2
    call = fake_pipeline.calls[0]
    assert call["pdf_folder"] == "/pdf_in/Class_11_Economics"
    assert call["output_root"] is None
    # The folder name -- not anything inferred from the PDFs -- is the book title.
    assert call["book_title_override"] == "Class_11_Economics"


def test_process_book_legacy_book_passes_no_override(fake_pipeline):
    book = book_orchestrator.Book(name=None, pdf_folder="/pdf_in", output_root=None)

    book_orchestrator.process_book(book, use_vlm=False, page_batch_size=6, force=False)

    call = fake_pipeline.calls[0]
    assert call["book_title_override"] is None
    assert call["output_root"] is None


def test_process_book_isolates_failure_and_keeps_going(fake_pipeline, capsys):
    fake_pipeline.raise_for_folder = "/pdf_in/Bad_Book"
    book = book_orchestrator.Book(name="Bad_Book", pdf_folder="/pdf_in/Bad_Book",
                                   output_root=None)

    stats = book_orchestrator.process_book(book, use_vlm=False, page_batch_size=6, force=False)

    assert stats["error"]
    assert "FAILED" in capsys.readouterr().out


def test_run_processes_every_discovered_book_and_survives_one_failure(tmp_path, fake_pipeline, capsys):
    pdf_in = tmp_path / "pdf_in"
    good_folder = str(pdf_in / "Good_Book")
    bad_folder = str(pdf_in / "Bad_Book")
    _touch_pdf(os.path.join(good_folder, "ch1.pdf"))
    _touch_pdf(os.path.join(bad_folder, "ch1.pdf"))
    fake_pipeline.raise_for_folder = bad_folder

    all_stats = book_orchestrator.run(use_vlm=False, page_batch_size=6, force=False,
                                       pdf_input_folder=str(pdf_in))

    assert len(all_stats) == 2  # both books attempted despite the failure
    assert len(fake_pipeline.calls) == 2
    out = capsys.readouterr().out
    assert "Found 2 books." in out
    assert "Processing Book 1/2" in out
    assert "Processing Book 2/2" in out


def test_run_with_no_books_found_does_not_crash(tmp_path, fake_pipeline, capsys):
    pdf_in = tmp_path / "pdf_in"
    os.makedirs(str(pdf_in))

    all_stats = book_orchestrator.run(use_vlm=False, page_batch_size=6, force=False,
                                       pdf_input_folder=str(pdf_in))

    assert all_stats == []
    assert fake_pipeline.calls == []
    assert "Found 0 books." in capsys.readouterr().out
