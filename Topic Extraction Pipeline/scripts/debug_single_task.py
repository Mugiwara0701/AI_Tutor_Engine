"""
scripts/debug_single_task.py — fast single-task iteration loop against the
REAL Qwen model, without running the whole pipeline.

Loads the model once (same singleton as pipeline.py), grabs one page from a
PDF already in pdf_in/, and runs exactly one prompt_manager task against it.
Prints the RAW model output (before any cleanup/parsing) so you can see
directly what Qwen actually said, plus the cleaned/parsed result and any
validation errors.

Usage (from the project root, with your venv active):
    python scripts/debug_single_task.py figure_analysis
    python scripts/debug_single_task.py topic_semantics
    python scripts/debug_single_task.py concept_extraction

In VS Code: set a breakpoint on the `result = manager.run(...)` line below,
hit F5 with a "Python File" debug config, and inspect `result.raw_model_output`,
`result.validation_errors`, etc. in the Debug Console.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from prompt_manager import PromptManager, TaskContext
from prompt_manager.adapters import QwenAdapter
from config import PDF_INPUT_FOLDER


def _first_pdf_page():
    pdfs = sorted(glob.glob(os.path.join(PDF_INPUT_FOLDER, "*.pdf")))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {PDF_INPUT_FOLDER}. Copy one in first.")
    # Prefer a non-prelims file so the page actually has body content.
    pdf_path = next((p for p in pdfs if not p.lower().endswith("ps.pdf")), pdfs[0])
    doc = fitz.open(pdf_path)
    page = doc[min(2, doc.page_count - 1)]  # skip the very first page (often just a title)
    pix = page.get_pixmap(matrix=fitz.Matrix(130 / 72.0, 130 / 72.0))
    from PIL import Image
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    print(f"Using page {page.number} of {os.path.basename(pdf_path)}")
    return img


# One canned TaskContext per task, so you can just run `python
# scripts/debug_single_task.py <task_name>` for any registered task.
TASK_CONTEXTS = {
    "topic_semantics": lambda img: TaskContext(
        variables={"topic_title": "Test Topic", "topic_body_preview": "Sample body text for testing."},
        images=[img]),
    "figure_analysis": lambda img: TaskContext(
        variables={"caption": "Fig 1.1 Test figure"}, images=[img]),
    "table_analysis": lambda img: TaskContext(
        variables={"caption": "Table 1.1 Test table", "rows": 4, "columns": 3}, images=[img]),
    "equation_analysis": lambda img: TaskContext(
        variables={"raw_text_hint": "Y = C + I + G + NX"}, images=[img]),
    "concept_extraction": lambda img: TaskContext(
        variables={"chapter_title": "Test Chapter", "topic_title": "Test Topic",
                   "topic_body_text": "Sample body text about GDP and national income.",
                   "prior_concepts": []}, images=[]),
    "chapter_ai_metadata": lambda img: TaskContext(
        variables={"topic_titles": ["Intro", "GDP"], "num_figures": 2, "num_tables": 1,
                   "num_equations": 1}, images=[]),
    "generation_metadata": lambda img: TaskContext(
        variables={"chapter_title": "Test Chapter", "chapter_type": "conceptual",
                   "visual_dependency": "high", "formula_dependency": "high"}, images=[]),
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in TASK_CONTEXTS:
        print(f"Usage: python scripts/debug_single_task.py <task_name>")
        print(f"Available: {sorted(TASK_CONTEXTS)}")
        raise SystemExit(1)

    task_name = sys.argv[1]
    img = _first_pdf_page()
    ctx = TASK_CONTEXTS[task_name](img)

    manager = PromptManager(QwenAdapter())
    result = manager.run(task_name, ctx)   # <-- breakpoint here

    print("\n=== RAW MODEL OUTPUT ===")
    print(result.raw_model_output)
    print(f"\n=== success={result.success} retry_count={result.retry_count} ===")
    if not result.success:
        print("validation_errors:", result.validation_errors)
    else:
        print("parsed_output:", result.parsed_output)


if __name__ == "__main__":
    main()