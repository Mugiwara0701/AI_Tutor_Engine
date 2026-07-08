"""
modules/recognizers/visual_recognizers.py — candidate recognizers for
visual block types ("Table", "Figure", "Diagram", "Flowchart",
"Decision Tree"): flowchart, graph, circuit diagram, concept table, and a
generic fallback that always matches (at low confidence) so these block
types never end up with nothing extracted.

All of these key off caption/body vocabulary, never subject metadata —
a "Diagram" block captioned "Circuit for Ohm's law verification" is
recognized as a circuit diagram regardless of whether the chapter/subject
is labeled "Physics" or just "Science".
"""
import re
from typing import Optional

from modules.stage_a_geometry import Block
from modules.recognizers.base import (
    VisualFamilyRecognizer, RecognitionResult, block_raw_texts, block_deterministic_visual,
)

_FLOWCHART_KEYWORDS_RE = re.compile(r"\b(flow\s*chart|flowchart|start\b|end\b|decision\b|process\b)\b", re.I)
_GRAPH_KEYWORDS_RE = re.compile(r"\b(graph|axis|x-axis|y-axis|plot|curve|slope)\b", re.I)
_CIRCUIT_KEYWORDS_RE = re.compile(r"\b(circuit|resistor|voltmeter|ammeter|capacitor|battery|ohm)\b", re.I)
_CONCEPT_TABLE_KEYWORDS_RE = re.compile(
    r"\b(comparison|difference between|differences?|types? of|classification|versus|vs\.?)\b", re.I)


class FlowchartRecognizer(VisualFamilyRecognizer):
    name = "flowchart"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        if not _FLOWCHART_KEYWORDS_RE.search(caption):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "flowchart"
        return RecognitionResult(0.65, data, self.educational_object_type, self.name)


class GraphRecognizer(VisualFamilyRecognizer):
    name = "graph"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        if not _GRAPH_KEYWORDS_RE.search(caption):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "graph"
        return RecognitionResult(0.6, data, self.educational_object_type, self.name)


class CircuitDiagramRecognizer(VisualFamilyRecognizer):
    name = "circuit_diagram"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        if not _CIRCUIT_KEYWORDS_RE.search(caption):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "circuit_diagram"
        return RecognitionResult(0.6, data, self.educational_object_type, self.name)


class ConceptTableRecognizer(VisualFamilyRecognizer):
    """A Table block whose caption/leading text reads as a comparison or
    classification table ("Comparison of ...", "Types of ...", "Difference
    between ... and ...") is recognized as a reusable Concept Table,
    scored above the GenericVisualRecognizer fallback."""
    name = "concept_table"
    use_table_semantics = True

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        leading_text = " ".join(block_raw_texts(block)[:2])
        if not _CONCEPT_TABLE_KEYWORDS_RE.search(f"{caption} {leading_text}"):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "concept_table"
        return RecognitionResult(0.7, data, self.educational_object_type, self.name)


class GenericVisualRecognizer(VisualFamilyRecognizer):
    """Always matches, at the same confidence (0.5) and with the same
    caption+metadata payload the pre-modular `_extract_visual_deterministic`
    produced for every Table/Figure/Diagram by default. Registered last /
    lowest-priority for every visual block type so a block that doesn't
    match any more specific recognizer still gets this baseline extraction
    instead of nothing."""
    name = "generic_visual"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        data = block_deterministic_visual(block)
        return RecognitionResult(0.5, data, self.educational_object_type, self.name)
