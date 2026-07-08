"""
tests/test_master_json_restoration.py — regression test for the fix
documented in REGRESSION_AUDIT.md: assemble_chapter_json/write_chapter_json
(the full Master JSON shape) must be the pipeline's actual output again,
and must additionally carry the Stage A-E `blocks` / `educational_objects`
/ `validation_report` output rather than that output living in a separate
document that replaced the Master JSON.
"""
import inspect

import pipeline
import modules.json_writer as json_writer
from modules.stage_a_geometry import Block


def _fake_structure():
    class FakeStructure:
        num_pages = 1
        page_sizes = {0: (100.0, 200.0)}
        page_word_counts = {0: 10}
        book_title = "Test Book"
        subject = "economics"
        klass = "12"
        language = "en"
        chapter_number = 1
        chapter_title = "intro"
        toc_matched = True
    return FakeStructure()


def test_pipeline_no_longer_exposes_debug_export_blocks_params():
    """process_chapter/process_all_pdfs used to gate the Stage A/B/C block
    graph behind debug/export_blocks flags on the *replacement* Educational
    Objects Document. Now that blocks are folded unconditionally into the
    Master JSON, those flags no longer need to exist on these signatures."""
    sig = inspect.signature(pipeline.process_chapter)
    assert "debug" not in sig.parameters
    assert "export_blocks" not in sig.parameters


def test_pipeline_calls_assemble_chapter_json_not_educational_objects_document():
    """The regression: pipeline.py used to call
    assemble_educational_objects_document/write_educational_objects_json
    instead of assemble_chapter_json/write_chapter_json. Source-level check
    that the Master JSON path is what's wired up now."""
    source = inspect.getsource(pipeline.process_chapter)
    assert "json_writer.assemble_chapter_json(" in source
    assert "json_writer.write_chapter_json(" in source
    assert "assemble_educational_objects_document" not in source
    assert "write_educational_objects_json" not in source


def test_assemble_chapter_json_includes_blocks_and_educational_objects():
    blk = Block(block_id="b1", parent=None, block_type="Formula Box", priority="high",
                confidence=0.9, page=0, page_end=0, bbox=(0, 0, 10, 10), lines=[], children=[],
                grouping_meta={})
    eo = {"id": "b1-eo", "block_id": "b1", "block_type": "Formula Box", "priority": "high",
          "educational_object_type": "formula_or_procedure", "confidence": 0.9}
    vr = {"input_count": 1, "output_count": 1, "removed_duplicate_formulas": 0,
          "removed_duplicate_definitions": 0, "removed_bare_arithmetic": 0, "warnings": []}

    result = json_writer.assemble_chapter_json(
        structure=_fake_structure(), pdf_path="x.pdf", topics_semantic=[], concepts=[], glossary=[],
        definitions=[], examples=[], activities=[], figures=[], tables=[], equations=[], diagrams=[],
        charts=[], graphs=[], maps=[], timelines=[], boxes=[], notes=[], warnings=[],
        learning_graph={"nodes": [], "edges": []}, concept_graph={"nodes": [], "edges": []},
        semantic_index=[], ai_metadata={}, generation_metadata={}, quality={"overall": 0.5},
        extraction_logs={}, ocr_engine_name="test", vlm_model_id="disabled", processing_time_seconds=1.0,
        blocks=[blk], educational_objects=[eo], validation_report=vr,
    )

    assert result["blocks"] == [{
        "block_id": "b1", "parent": None, "block_type": "Formula Box", "priority": "high",
        "confidence": 0.9, "page": 0, "page_end": 0,
        "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10, "page": 0}, "child_block_ids": [],
    }]
    assert result["educational_objects"] == [eo]
    assert result["validation_report"] == vr

    # Every pre-existing Master JSON section must still be present.
    for key in ("topics", "concepts", "glossary", "figures", "tables", "equations",
                "learning_graph", "concept_graph", "semantic_index", "ai_metadata",
                "generation_metadata"):
        assert key in result

    is_valid, errors, normalized = json_writer.validate_chapter(result)
    assert is_valid, errors


def test_assemble_chapter_json_without_blocks_still_defaults_empty():
    """Backward compatibility: a caller that doesn't pass blocks/
    educational_objects/validation_report (the pre-fix call shape) must
    still get a valid Master JSON with empty defaults for the new fields."""
    result = json_writer.assemble_chapter_json(
        structure=_fake_structure(), pdf_path="x.pdf", topics_semantic=[], concepts=[], glossary=[],
        definitions=[], examples=[], activities=[], figures=[], tables=[], equations=[], diagrams=[],
        charts=[], graphs=[], maps=[], timelines=[], boxes=[], notes=[], warnings=[],
        learning_graph={"nodes": [], "edges": []}, concept_graph={"nodes": [], "edges": []},
        semantic_index=[], ai_metadata={}, generation_metadata={}, quality={"overall": 0.5},
        extraction_logs={}, ocr_engine_name="test", vlm_model_id="disabled", processing_time_seconds=1.0,
    )
    assert result["blocks"] == []
    assert result["educational_objects"] == []
    assert result["validation_report"] == {}
    is_valid, errors, normalized = json_writer.validate_chapter(result)
    assert is_valid, errors


# ---------------------------------------------------------------------------
# ISSUE 1 / ISSUE 7: Stage A/B/C must run exactly once per chapter, and must
# run BEFORE the flat `equations` list is built so that list can consult
# Stage B's classification instead of unconditionally calling
# equation_analysis for every detected equation region (which is what
# produced the "Stage A/B/C ... then equation_analysis runs again"
# duplicate-cost symptom the audit traced this to -- see pipeline.py's
# Stage A comment and modules/equation_intent.py).
# ---------------------------------------------------------------------------
def test_stage_a_b_c_each_invoked_exactly_once_in_process_chapter():
    source = inspect.getsource(pipeline.process_chapter)
    assert source.count("stage_a_geometry.build_hierarchical_blocks(") == 1
    assert source.count("stage_b_classify.classify_blocks(") == 1
    assert source.count("stage_c_priority.assign_priority(") == 1


def test_stage_a_b_c_run_before_flat_equations_loop():
    source = inspect.getsource(pipeline.process_chapter)
    stage_a_pos = source.index("stage_a_geometry.build_hierarchical_blocks(")
    stage_b_pos = source.index("stage_b_classify.classify_blocks(")
    stage_c_pos = source.index("stage_c_priority.assign_priority(")
    equations_loop_pos = source.index('for idx, region in enumerate(layout["equations"]):')
    assert stage_a_pos < stage_b_pos < stage_c_pos < equations_loop_pos


def test_flat_equations_loop_gates_vlm_via_equation_intent():
    """The flat equations builder must consult the dynamic educational-
    intent classifier (ISSUE 3/4) rather than call
    semantic_processor.process_equation_semantics unconditionally for
    every region."""
    source = inspect.getsource(pipeline.process_chapter)
    equations_loop = source[source.index('for idx, region in enumerate(layout["equations"]):'):
                             source.index("# ---- content blocks -> final records")]
    assert "equation_intent.introduces_reusable_knowledge(" in equations_loop
    assert "vlm_analysis_skipped" in equations_loop
    # The equation record must still be appended even when the VLM call is
    # skipped -- Issue 5's "no information should disappear" requirement.
    assert equations_loop.count("equations.append(") == 1
