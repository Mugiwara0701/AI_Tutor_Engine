"""
tests/test_semantic_processor.py — verifies the pipeline-reconnect milestone:
every VLM call in modules/semantic_processor.py now goes through
prompt_manager instead of calling modules.vlm_inference directly, while its
public function signatures and returned flat-dict shapes stay unchanged.

Two layers, matching tests/test_prompt_manager.py's existing style:
  - Unit tests use a FakeAdapter (no GPU, no real Qwen) to exercise
    semantic_processor's own logic: task/context selection, evidence-triple
    unwrapping, word-cap enforcement, and graceful {} fallback on failure.
  - One integration test proves the full chain end-to-end:
    semantic_processor -> prompt_manager -> qwen_adapter -> Qwen -> TaskResult,
    using the REAL PromptManager and REAL QwenAdapter, with only
    modules.vlm_inference.generate() (the actual model call) mocked out --
    everything above and below that single seam is real production code.

Run: python -m pytest tests/test_semantic_processor.py -v
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import fitz

from modules import semantic_processor
from modules.pdf_parser import TopicRecord
from modules.layout_detector import VisualRegion
from prompt_manager.model_adapter import ModelAdapter, AdapterResponse
from prompt_manager.prompt_manager import PromptManager
from prompt_manager.adapters.qwen_adapter import QwenAdapter


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def blank_doc(tmp_path):
    """A real (tiny) fitz.Document, since render_full_page/render_page_crop
    genuinely rasterize a page -- no point faking PyMuPDF itself."""
    doc = fitz.open()
    doc.new_page(width=400, height=600)
    yield doc
    doc.close()


def make_topic(**overrides):
    defaults = dict(
        id="t1", title="National Income", numbering="1.1", level=1, parent=None,
        page_start=0, page_end=0, bbox=(10, 10, 200, 200), reading_order=0,
        body_text="National income measures total output.", confidence=0.6, signals={},
    )
    defaults.update(overrides)
    return TopicRecord(**defaults)


def make_region(**overrides):
    defaults = dict(kind="figure", page=0, bbox=(10, 10, 200, 200), caption="Fig 1.1", title="", extra={})
    defaults.update(overrides)
    return VisualRegion(**defaults)


class FakeAdapter(ModelAdapter):
    """Same pattern as tests/test_prompt_manager.py's FakeAdapter: returns
    canned raw text, one response per call, and parses it the way a real
    adapter would -- so semantic_processor is exercised through the real
    PromptManager retry/validation path without needing Qwen."""
    adapter_id = "fake-adapter-for-semantic-processor-tests"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, prompt, images=None, max_new_tokens=None):
        self.calls.append({"prompt": prompt, "images": images})
        if not self._responses:
            raise RuntimeError("FakeAdapter ran out of canned responses")
        return self._responses.pop(0)

    def generate_json(self, prompt, images=None, max_new_tokens=None):
        raw = self.generate(prompt, images=images, max_new_tokens=max_new_tokens)
        try:
            return AdapterResponse(success=True, raw_output=raw, cleaned_output=raw,
                                    parsed_output=json.loads(raw))
        except Exception:
            return AdapterResponse(success=False, raw_output=raw, cleaned_output=raw,
                                    parsed_output=None, error_message="not valid JSON")


def _use_fake_manager(monkeypatch, responses):
    manager = PromptManager(FakeAdapter(responses))
    monkeypatch.setattr(semantic_processor, "_get_prompt_manager", lambda: manager)
    return manager


TRIPLE = lambda v, c=0.8, e="x": {"value": v, "confidence": c, "evidence_basis": e}

VALID_FIGURE_RESPONSE = json.dumps({
    "figure_type": TRIPLE("diagram"),
    "semantic_description": TRIPLE("Shows the circular flow of income " * 3),  # long, to test word cap
    "key_visual_elements": [TRIPLE("arrow from household to firm")],
    "educational_purpose": TRIPLE("Illustrates money flow."),
    "concepts": ["circular flow"],
    "related_topics": ["national income"],
    "importance": TRIPLE("high", 0.9),
    "difficulty": TRIPLE("medium", 0.7),
    "animation_candidate": TRIPLE(True, 0.6),
})

VALID_TABLE_RESPONSE = json.dumps({
    "table_type": TRIPLE("data_table", 0.9),
    "semantic_description": TRIPLE("Shows sector-wise income contribution."),
    "educational_purpose": TRIPLE("Compares sectors."),
    "concepts": ["GDP"],
})

VALID_EQUATION_RESPONSE = json.dumps({
    "latex": TRIPLE("Y = C + I + G + NX", 0.95),
    "spoken_form": TRIPLE("Y equals C plus I plus G plus N X"),
    "variables": ["Y: total output", "C: consumption"],
    "semantic_meaning": TRIPLE("National income identity."),
})

VALID_TOPIC_RESPONSE = json.dumps({
    "semantic_summary": TRIPLE("Explains how national income is measured " * 3),
    "visual_summary": TRIPLE("A flow diagram of income."),
    "concepts": ["national income"],
    "glossary_terms": ["GDP"],
    "detected_entities": [],
    "prerequisites": [],
    "related_topics": [],
    "educational_purpose": TRIPLE("Introduces core measurement concepts."),
})

VALID_CHAPTER_METADATA_RESPONSE = json.dumps({
    "chapter_type": TRIPLE("conceptual", 0.7),
    "knowledge_density": TRIPLE("medium"),
    "overall_complexity": TRIPLE("medium"),
    "visual_dependency": TRIPLE("high", 0.8),
    "formula_dependency": TRIPLE("high", 0.9),
    "memory_dependency": TRIPLE("low"),
    "calculation_dependency": TRIPLE("high"),
    "real_world_relevance": TRIPLE("high"),
    "important_concepts": ["GDP"],
    "likely_confusing_concepts": [],
    "visual_priority_topics": [],
    "concept_progression": ["National Income"],
    "interdisciplinary_links": [],
})

VALID_GENERATION_METADATA_RESPONSE = json.dumps({
    "preferred_visual_types": ["diagram"],
    "visual_priority": ["circular flow diagram"],
    "real_world_domains": ["household budgeting"],
})


# ---------------------------------------------------------------------------
# process_figure_semantics / process_table_semantics / process_equation_semantics
# ---------------------------------------------------------------------------
def test_process_figure_semantics_routes_through_prompt_manager_and_unwraps(monkeypatch, blank_doc):
    manager = _use_fake_manager(monkeypatch, [VALID_FIGURE_RESPONSE])
    region = make_region(kind="figure", caption="Fig 1.1 Circular flow")

    result = semantic_processor.process_figure_semantics(blank_doc, region)

    assert manager.adapter.calls, "prompt_manager's adapter should have been invoked"
    # flat, plain values -- not evidence-triples -- exactly what json_writer/pipeline expect
    assert result["figure_type"] == "diagram"
    assert result["importance"] == "high"
    assert result["animation_candidate"] is True
    assert result["concepts"] == ["circular flow"]
    # word cap enforced on the unwrapped value
    assert len(result["semantic_description"].split()) <= semantic_processor.MAX_SEMANTIC_DESCRIPTION_WORDS
    # top-level confidence synthesized from the per-field triples
    assert 0.0 <= result["confidence"] <= 1.0


def test_process_table_semantics_routes_through_prompt_manager(monkeypatch, blank_doc):
    _use_fake_manager(monkeypatch, [VALID_TABLE_RESPONSE])
    region = make_region(kind="table", caption="Table 1.1", extra={"rows": 5, "columns": 3})

    result = semantic_processor.process_table_semantics(blank_doc, region)

    assert result["table_type"] == "data_table"
    assert result["concepts"] == ["GDP"]
    assert result["semantic_description"]


def test_process_equation_semantics_routes_through_prompt_manager(monkeypatch, blank_doc):
    semantic_processor.reset_chapter_state()
    _use_fake_manager(monkeypatch, [VALID_EQUATION_RESPONSE])
    region = make_region(kind="equation", caption="", extra={"raw_text": "Y=C+I+G+NX"})

    result = semantic_processor.process_equation_semantics(blank_doc, region)

    assert result["latex"] == "Y = C + I + G + NX"
    assert result["variables"] == ["Y: total output", "C: consumption"]


def test_process_equation_semantics_is_cached_per_chapter(monkeypatch, blank_doc):
    """ISSUE 1 fix: two independent call sites (the flat top-level
    `equations` builder in pipeline.py and Stage D's
    FormulaFamilyRecognizer.vlm_fallback) can both ask for semantics on the
    exact same (page, bbox) equation region. Only ONE VLM call should ever
    happen for that region within a single chapter."""
    semantic_processor.reset_chapter_state()
    manager = _use_fake_manager(monkeypatch, [VALID_EQUATION_RESPONSE])
    region_a = make_region(kind="equation", caption="", extra={"raw_text": "Y=C+I+G+NX"})
    # A second VisualRegion instance with the identical page/bbox -- as it
    # would be if built independently by two different call sites from the
    # same underlying layout-detected region.
    region_b = make_region(kind="equation", caption="", extra={"raw_text": "Y=C+I+G+NX"})

    first = semantic_processor.process_equation_semantics(blank_doc, region_a)
    second = semantic_processor.process_equation_semantics(blank_doc, region_b)

    assert first == second
    assert len(manager.adapter.calls) == 1, "equation_analysis was called more than once for the same region"


def test_process_equation_semantics_cache_is_reset_between_chapters(monkeypatch, blank_doc):
    """The cache must never leak across chapters -- a different chapter can
    legitimately have an unrelated equation at the same (page, bbox)."""
    semantic_processor.reset_chapter_state()
    manager = _use_fake_manager(monkeypatch, [VALID_EQUATION_RESPONSE, VALID_EQUATION_RESPONSE])
    region = make_region(kind="equation", caption="", extra={"raw_text": "Y=C+I+G+NX"})

    semantic_processor.process_equation_semantics(blank_doc, region)
    semantic_processor.reset_chapter_state()  # simulates pipeline.py starting the next chapter
    semantic_processor.process_equation_semantics(blank_doc, region)

    assert len(manager.adapter.calls) == 2


def test_figure_semantics_falls_back_gracefully_after_exhausted_retries(monkeypatch, blank_doc):
    """Old behaviour: an unparsable VLM response resulted in a bare empty
    dict (_safe_json's fallback), never a crash. That still must never
    crash -- but per the JSON-repair-layer fix (ISSUE 2), a failure must no
    longer silently discard the model's raw output either; it's preserved
    (under namespaced keys) instead of the block's semantics simply
    vanishing, alongside the always-set semantic_description field the
    function unconditionally normalizes."""
    _use_fake_manager(monkeypatch, ["not json", "still not json"])
    region = make_region(kind="figure")

    result = semantic_processor.process_figure_semantics(blank_doc, region)

    assert result["semantic_description"] == ""
    assert result["_vlm_failed"] is True
    assert result["_vlm_raw_output"] == "still not json"


# ---------------------------------------------------------------------------
# process_topic_semantics
# ---------------------------------------------------------------------------
def test_process_topic_semantics_routes_through_prompt_manager(monkeypatch, blank_doc):
    manager = _use_fake_manager(monkeypatch, [VALID_TOPIC_RESPONSE])
    topic = make_topic()

    result = semantic_processor.process_topic_semantics(blank_doc, topic)

    call = manager.adapter.calls[0]
    assert "National Income" in call["prompt"]
    assert call["images"], "topic_semantics expects a page image"
    assert result["glossary_terms"] == ["GDP"]
    assert len(result["semantic_summary"].split()) <= semantic_processor.MAX_SEMANTIC_DESCRIPTION_WORDS


# ---------------------------------------------------------------------------
# process_chapter_ai_metadata / process_generation_metadata
# ---------------------------------------------------------------------------
def test_process_chapter_ai_metadata_routes_through_prompt_manager(monkeypatch):
    _use_fake_manager(monkeypatch, [VALID_CHAPTER_METADATA_RESPONSE])

    result = semantic_processor.process_chapter_ai_metadata(
        ["National Income", "Circular Flow"], num_figures=2, num_tables=1, num_equations=1)

    assert result["chapter_type"] == "conceptual"
    assert result["visual_dependency"] == "high"
    assert result["concept_progression"] == ["National Income"]


def test_process_generation_metadata_uses_prior_ai_metadata(monkeypatch):
    manager = _use_fake_manager(monkeypatch, [VALID_GENERATION_METADATA_RESPONSE])
    ai_metadata = {"chapter_type": "conceptual", "visual_dependency": "high", "formula_dependency": "high"}

    result = semantic_processor.process_generation_metadata("Macroeconomics", ai_metadata)

    call = manager.adapter.calls[0]
    assert "conceptual" in call["prompt"]
    assert result["visual_priority"] == ["circular flow diagram"]
    assert "teacher_style" not in result
    assert "quiz_focus_topics" not in result


# ---------------------------------------------------------------------------
# Integration test: semantic_processor -> prompt_manager -> qwen_adapter ->
# Qwen -> TaskResult, all real code except the actual model.generate() call.
# ---------------------------------------------------------------------------
def test_full_chain_semantic_processor_to_prompt_manager_to_qwen_adapter(monkeypatch, blank_doc):
    """Proves the reconnected path end-to-end with REAL PromptManager and
    REAL QwenAdapter objects (the ones semantic_processor now actually
    builds via _get_prompt_manager). Only modules.vlm_inference.generate --
    the function that would otherwise load Qwen2.5-VL-3B and run inference
    on a GPU -- is replaced with a stub, since no GPU/model is available in
    CI. Everything else (task lookup, template rendering, the adapter's
    markdown-fence/trailing-comma cleanup, JSON parsing, output_contract
    validation, retry handling, and semantic_processor's own triple
    unwrapping) is exercised for real.
    """
    from modules import vlm_inference

    calls = {"n": 0}

    def fake_generate(prompt, images=None, max_new_tokens=None):
        calls["n"] += 1
        assert "Fig 1.1" in prompt  # region.caption really made it into the rendered prompt
        # Simulate Qwen wrapping JSON in a markdown fence -- qwen_adapter's
        # real cleanup step must strip this, not semantic_processor.
        return "```json\n" + VALID_FIGURE_RESPONSE + "\n```"

    monkeypatch.setattr(vlm_inference, "generate", fake_generate)
    # Ensure semantic_processor builds a *real* PromptManager(QwenAdapter()),
    # not a leftover instance from an earlier test in this module.
    monkeypatch.setattr(semantic_processor, "_PROMPT_MANAGER", None)

    region = make_region(kind="figure", caption="Fig 1.1 Circular flow")
    result = semantic_processor.process_figure_semantics(blank_doc, region)

    assert calls["n"] == 1, "should succeed on the first attempt, no retry needed"
    assert result["figure_type"] == "diagram"
    assert result["importance"] == "high"
    assert isinstance(result["confidence"], float)

    manager = semantic_processor._get_prompt_manager()
    assert isinstance(manager, PromptManager)
    assert isinstance(manager.adapter, QwenAdapter)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
