"""
tests/test_kg_readiness.py — exercises modules/kg_readiness.py, the Part 2
Phase-1 -> Phase-2 readiness enrichment layer.

Explicitly verifies:
  - context-preservation fields are attached (parent chapter/heading/
    sub-heading, hierarchy path, reading/block order, local context, ...)
  - KG-readiness semantic metadata is attached (educational role, concept
    relation flags, belongs_to, visual/table support, prerequisite/
    dependency candidates, cross references, ...)
  - NOTHING pre-existing on an educational object is removed or
    overwritten
  - no graph nodes/edges are ever produced (this module must stay
    metadata-only, per the task spec)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import kg_readiness as kg
from modules.stage_a_geometry import Block
from modules.pdf_parser import Line


def _line(text, page=3):
    return Line(text=text, size=11, max_size=11, bold=False, font="Test",
                page=page, y=100.0, page_height=800.0, bbox=(0, 0, 100, 10))


def _topics():
    return [
        {"id": "t-heading-1", "title": "Motion", "numbering": "2.1", "level": 1,
         "parent": None, "page_start": 1, "page_end": 5,
         "prerequisites": ["Kinematics basics"], "related_topics": ["Force"]},
        {"id": "t-subheading-1", "title": "Uniform Motion", "numbering": "2.1.1", "level": 2,
         "parent": "t-heading-1", "page_start": 2, "page_end": 4,
         "prerequisites": [], "related_topics": []},
    ]


def _blocks():
    definition_block = Block(
        block_id="blk-def-1", page=3, bbox=(0, 0, 100, 20),
        lines=[_line("Velocity is defined as the rate of change of displacement.")],
        parent=None, block_type="Definition", confidence=0.8,
    )
    formula_block = Block(
        block_id="blk-formula-1", page=3, bbox=(0, 25, 100, 40),
        lines=[_line("Using the above formula, v = d/t.")],
        parent=None, block_type="Formula Box", confidence=0.9,
    )
    worked_example_block = Block(
        block_id="blk-example-1", page=3, bbox=(0, 45, 100, 60),
        lines=[_line("As shown in Figure 2.1, refer to Table 1 for values.")],
        parent=None, block_type="Worked Example", confidence=0.7,
    )
    return [definition_block, formula_block, worked_example_block]


def _educational_objects():
    return [
        {"id": "eo-1", "block_id": "blk-def-1", "page": 3, "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
         "educational_object_type": "concept", "block_type": "Definition",
         "confidence": 0.8, "recognizer": "ConceptRecognizer", "source": "text",
         "term": {"value": "Velocity", "confidence": 0.8, "evidence_basis": "x"}},
        {"id": "eo-2", "block_id": "blk-formula-1", "page": 3, "bbox": {"x0": 0, "y0": 25, "x1": 100, "y1": 40},
         "educational_object_type": "formula_or_procedure", "block_type": "Formula Box",
         "confidence": 0.9, "recognizer": "FormulaRecognizer", "source": "text"},
        {"id": "eo-3", "block_id": "blk-example-1", "page": 3, "bbox": {"x0": 0, "y0": 45, "x1": 100, "y1": 60},
         "educational_object_type": "unclassified_high_value", "block_type": "Worked Example",
         "confidence": 0.7, "recognizer": "GenericRecognizer", "source": "text"},
    ]


def test_enrich_preserves_all_original_fields():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    original = _educational_objects()
    for orig, enr in zip(original, enriched):
        for key, val in orig.items():
            assert enr[key] == val, f"original field {key!r} was altered"


def test_enrich_attaches_context_preservation_fields():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo1 = next(e for e in enriched if e["id"] == "eo-1")
    assert eo1["parent_chapter"] == "Motion in a Line"
    assert eo1["parent_heading"] == "Motion"
    assert eo1["parent_sub_heading"] == "Uniform Motion"
    assert eo1["hierarchy_path"] == ["Motion in a Line", "Motion", "Uniform Motion"]
    assert eo1["page_id"] == "page-3"
    assert eo1["source_block_id"] == "blk-def-1"
    assert isinstance(eo1["reading_order"], int)
    assert isinstance(eo1["block_order"], int)
    assert "Velocity" in eo1["local_context"]
    assert eo1["semantic_topic"] == "Uniform Motion"


def test_enrich_attaches_educational_role():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    roles = {e["id"]: e["educational_role"] for e in enriched}
    assert roles["eo-1"] == "Introduces Knowledge"
    assert roles["eo-2"] == "Explains Knowledge"
    assert roles["eo-3"] == "Worked Example"


def test_enrich_detects_cross_references_without_resolving_them():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo3 = next(e for e in enriched if e["id"] == "eo-3")
    ref_types = {r["type"] for r in eo3["cross_references"]}
    assert "figure" in ref_types
    assert "table" in ref_types
    # Metadata only -- never resolved into an edge/target id.
    for ref in eo3["cross_references"]:
        assert set(ref.keys()) == {"type", "mention"}


def test_enrich_uses_formula_cross_reference():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo2 = next(e for e in enriched if e["id"] == "eo-2")
    # formula_or_procedure objects reference themselves as the formula used
    assert eo2["uses_formula"] == ["eo-2"]


def test_enrich_belongs_to_and_associated_fields():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo1 = next(e for e in enriched if e["id"] == "eo-1")
    assert eo1["belongs_to"] == {"topic": "t-subheading-1", "heading": "Motion", "chapter": "Motion in a Line"}
    assert eo1["associated_topic"] == "Uniform Motion"
    assert eo1["associated_chapter"] == "Motion in a Line"


def test_enrich_prerequisite_and_dependency_candidates_propagate_from_topic():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo1 = next(e for e in enriched if e["id"] == "eo-1")
    # eo-1's page (3) only matches the sub-heading (page 2-4), which has no
    # prerequisites of its own -- propagation is per-matched-topic, not a
    # blind merge up the whole chain, so this should be empty here.
    assert eo1["prerequisite_candidates"] == []


def test_enrich_visual_and_table_support():
    figures = [{"id": "fig-1", "page": 3}]
    tables = [{"id": "tbl-1", "page": 3}]
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line",
                                               figures=figures, tables=tables)
    eo1 = next(e for e in enriched if e["id"] == "eo-1")
    assert eo1["visual_support"] is True
    assert eo1["figure_support"] == ["fig-1"]
    assert eo1["table_support"] == ["tbl-1"]


def test_enrich_nearby_educational_objects_finds_siblings():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    eo1 = next(e for e in enriched if e["id"] == "eo-1")
    assert "eo-2" in eo1["nearby_educational_objects"]


def test_enrich_never_produces_graph_nodes_or_edges_keys():
    enriched = kg.enrich_educational_objects(_educational_objects(), _blocks(), _topics(), "Motion in a Line")
    for eo in enriched:
        assert "graph_nodes" not in eo
        assert "graph_edges" not in eo
        assert "knowledge_graph" not in eo


def test_enrich_handles_missing_topic_and_block_gracefully():
    objs = [{"id": "eo-orphan", "block_id": "does-not-exist", "page": 999,
             "educational_object_type": "ambiguous"}]
    enriched = kg.enrich_educational_objects(objs, _blocks(), _topics(), "Motion in a Line")
    assert len(enriched) == 1
    assert enriched[0]["semantic_topic"] is None
    assert enriched[0]["local_context"] == ""
    assert enriched[0]["educational_role"] == "Reference"


def test_infer_educational_role_falls_back_to_object_type():
    assert kg.infer_educational_role({"educational_object_type": "visual"}) == "Illustration"
    assert kg.infer_educational_role({}) == "Reference"


def test_detect_cross_references_empty_text():
    assert kg.detect_cross_references("") == []
    assert kg.detect_cross_references(None) == []
