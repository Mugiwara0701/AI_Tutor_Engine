"""
tests/test_book_orchestrator_storage_gate.py — verifies book_orchestrator.
run()'s startup ordering: Initialize Storage -> Authenticate -> check/
run migration -> ONLY THEN start PDF extraction. A failure anywhere in
that gate must stop the run before any book is discovered or processed.

Storage/migration are stubbed at the book_orchestrator module level
(_ensure_storage_ready) so this exercises ORDERING, not the real Graph/
MSAL/migration implementation (covered in tests/test_migration.py).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_orchestrator  # noqa: E402


def _touch_pdf(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4 fake\n")


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def process_all_pdfs(self, use_vlm, page_batch_size, force, pdf_folder=None,
                          output_root=None, book_title_override=None):
        self.calls.append(pdf_folder)
        return {"found": 1, "written": 1, "failed": 0, "book_title": book_title_override}


@pytest.fixture
def fake_pipeline(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setitem(sys.modules, "pipeline", fake)
    return fake


def test_run_calls_storage_gate_before_discovering_or_processing_books(tmp_path, fake_pipeline, monkeypatch):
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "Class_12_Chemistry" / "ch1.pdf"))

    call_order = []

    def fake_gate():
        call_order.append("storage_gate")
        return "fake-storage-object"

    def fake_set_storage(storage):
        call_order.append(("set_storage", storage))

    original_discover = book_orchestrator.discover_books

    def spy_discover_books(*args, **kwargs):
        call_order.append("discover_books")
        return original_discover(*args, **kwargs)

    monkeypatch.setattr(book_orchestrator, "_ensure_storage_ready", fake_gate)
    monkeypatch.setattr(book_orchestrator.json_writer, "set_storage", fake_set_storage)
    monkeypatch.setattr(book_orchestrator, "discover_books", spy_discover_books)

    book_orchestrator.run(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=str(pdf_in))

    assert call_order[0] == "storage_gate"
    assert call_order[1] == ("set_storage", "fake-storage-object")
    assert call_order[2] == "discover_books"
    assert fake_pipeline.calls  # extraction did run, after the gate


def test_run_never_processes_any_book_if_storage_gate_fails(tmp_path, fake_pipeline, monkeypatch):
    pdf_in = tmp_path / "pdf_in"
    _touch_pdf(str(pdf_in / "Class_12_Chemistry" / "ch1.pdf"))

    def failing_gate():
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(book_orchestrator, "_ensure_storage_ready", failing_gate)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        book_orchestrator.run(use_vlm=False, page_batch_size=6, force=False, pdf_input_folder=str(pdf_in))

    # PDF extraction must never begin before migration completes.
    assert fake_pipeline.calls == []
