"""
task_registry.py — one entry per task. Adding a new task means adding a new
entry here (+ a template + a contract), never touching prompt_manager.py's
internals — same "extend, don't modify" principle as the rest of the design.

`required_context_vars` is what makes a TaskContext fail fast: if the caller
didn't supply everything the current template version declares it needs,
prompt_manager raises MissingContextError *before* any GPU call, per the
frozen design.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import os

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(_THIS_DIR, "prompts")


@dataclass(frozen=True)
class TaskSpec:
    name: str
    current_version: str          # e.g. "v1"
    required_context_vars: List[str]
    optional_context_vars: List[str] = field(default_factory=list)
    expects_images: bool = True   # False for pure-text tasks (e.g. recover_heading from OCR text only)
    output_contract_name: str = ""  # looked up in output_contract.CONTRACTS

    @property
    def template_dir(self) -> str:
        return os.path.join(PROMPTS_DIR, self.name)

    def template_path(self, version: Optional[str] = None) -> str:
        v = version or self.current_version
        return os.path.join(self.template_dir, f"{v}.txt")

    def meta_path(self, version: Optional[str] = None) -> str:
        v = version or self.current_version
        return os.path.join(self.template_dir, f"{v}.meta.json")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
TASKS = {
    "recover_chapter_title": TaskSpec(
        name="recover_chapter_title", current_version="v1",
        required_context_vars=["candidate_titles", "ocr_text_first_pages"],
        optional_context_vars=["book_title", "subject"],
        expects_images=True,
        output_contract_name="recover_chapter_title",
    ),
    "recover_heading": TaskSpec(
        name="recover_heading", current_version="v1",
        required_context_vars=["expected_level", "ocr_text_region", "nearby_headings"],
        optional_context_vars=["chapter_title"],
        expects_images=True,
        output_contract_name="recover_heading",
    ),
    # Added alongside the book-title/class VLM-recovery fallback in
    # pipeline.py (post Qwen2.5-VL preload): recovers a book's cover title
    # and/or class marking when they're set in a legacy non-Unicode font
    # and both the raw text layer and plain Tesseract OCR
    # (pdf_parser._ocr_recover_title/_ocr_recover_class) failed. One
    # full-page image, two fields recovered together -- see
    # semantic_processor.process_recover_book_cover_metadata()'s docstring
    # for why this is a full-page render rather than a tight title crop.
    "recover_book_cover_metadata": TaskSpec(
        name="recover_book_cover_metadata", current_version="v1",
        required_context_vars=["subject", "ocr_title_hint"],
        optional_context_vars=[],
        expects_images=True,
        output_contract_name="recover_book_cover_metadata",
    ),
    "concept_extraction": TaskSpec(
        name="concept_extraction", current_version="v1",
        required_context_vars=["topic_title", "topic_body_text"],
        optional_context_vars=["chapter_title", "prior_concepts"],
        expects_images=False,
        output_contract_name="concept_extraction",
    ),
    "figure_analysis": TaskSpec(
        name="figure_analysis", current_version="v1",
        required_context_vars=["caption"],
        optional_context_vars=["topic_title", "nearby_body_text"],
        expects_images=True,
        output_contract_name="figure_analysis",
    ),
    "table_analysis": TaskSpec(
        name="table_analysis", current_version="v1",
        required_context_vars=["caption", "rows", "columns"],
        optional_context_vars=["topic_title"],
        expects_images=True,
        output_contract_name="table_analysis",
    ),
    "equation_analysis": TaskSpec(
        name="equation_analysis", current_version="v1",
        required_context_vars=["raw_text_hint"],
        optional_context_vars=["topic_title"],
        expects_images=True,
        output_contract_name="equation_analysis",
    ),
    "relationship_extraction": TaskSpec(
        name="relationship_extraction", current_version="v1",
        required_context_vars=["entity_names"],
        optional_context_vars=["topic_title", "topic_body_text"],
        expects_images=False,
        output_contract_name="relationship_extraction",
    ),
    "entity_description": TaskSpec(
        name="entity_description", current_version="v1",
        required_context_vars=["entity_type", "caption"],
        optional_context_vars=["topic_title", "nearby_body_text"],
        expects_images=True,
        output_contract_name="entity_description",
    ),
    "visual_structure": TaskSpec(
        name="visual_structure", current_version="v1",
        required_context_vars=["caption"],
        optional_context_vars=["topic_title"],
        expects_images=True,
        output_contract_name="visual_structure",
    ),
    "semantic_metadata": TaskSpec(
        name="semantic_metadata", current_version="v1",
        required_context_vars=["concept_name", "source_references"],
        optional_context_vars=["topic_title"],
        expects_images=False,
        output_contract_name="semantic_metadata",
    ),
    # ------------------------------------------------------------------
    # Added during the pipeline-reconnect milestone so semantic_processor's
    # remaining VLM call sites (topic-level summary, chapter-level AI
    # planning metadata, generation metadata) go through the same
    # prompt_manager -> qwen_adapter -> validated-TaskResult path as
    # figure/table/equation analysis, instead of calling vlm_inference
    # directly. Same conventions as the tasks above (evidence-triple scalar
    # fields, plain-list list fields) -- no new conventions introduced.
    # ------------------------------------------------------------------
    "topic_semantics": TaskSpec(
        name="topic_semantics", current_version="v1",
        required_context_vars=["topic_title", "topic_body_preview"],
        optional_context_vars=[],
        expects_images=True,
        output_contract_name="topic_semantics",
    ),
    "chapter_ai_metadata": TaskSpec(
        name="chapter_ai_metadata", current_version="v1",
        required_context_vars=["topic_titles", "num_figures", "num_tables", "num_equations"],
        optional_context_vars=[],
        expects_images=False,
        output_contract_name="chapter_ai_metadata",
    ),
    "generation_metadata": TaskSpec(
        name="generation_metadata", current_version="v1",
        required_context_vars=["chapter_title", "chapter_type", "visual_dependency", "formula_dependency"],
        optional_context_vars=[],
        expects_images=False,
        output_contract_name="generation_metadata",
    ),
}


def get_task(task_name: str) -> TaskSpec:
    if task_name not in TASKS:
        raise KeyError(f"Unknown task '{task_name}'. Registered tasks: {sorted(TASKS)}")
    return TASKS[task_name]