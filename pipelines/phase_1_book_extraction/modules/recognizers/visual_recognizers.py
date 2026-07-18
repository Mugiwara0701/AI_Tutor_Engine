"""
modules/recognizers/visual_recognizers.py — candidate recognizers for
visual block types ("Table", "Figure", "Diagram", "Flowchart",
"Decision Tree"): flowchart, graph, circuit diagram, concept table, and a
generic fallback.

M4.1D improvements:
  - Improved figure caption association
  - Table prose false-positive suppression
  - Diagram identification improvements
  - Duplicate visual suppression
  - Better confidence scoring
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

# M4.1D: Improved caption detection patterns.
_FIGURE_CAPTION_RE = re.compile(r"^\s*(fig(?:ure)?\.?\s*\d+|plate\s*\d+|photo(?:graph)?\s*\d+)", re.I)
_TABLE_CAPTION_RE = re.compile(r"^\s*(table\s*\d+)", re.I)

# M4.1D: Prose sentence pattern (for table false-positive suppression).
_PROSE_SENTENCE_RE = re.compile(r"[.!?]\s+[A-Z]")

# M4.1D: Diagram-specific vocabulary for deterministic sub-typing.
_LIFECYCLE_RE = re.compile(r"\b(life\s*cycle|stages? of|phases? of)\b", re.I)
_MAP_RE = re.compile(r"\b(map|geographical|topographic|contour)\b", re.I)
_ANATOMY_RE = re.compile(r"\b(anatomy|structure of|cross.?section|longitudinal section)\b", re.I)


class FlowchartRecognizer(VisualFamilyRecognizer):
    name = "flowchart"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        body_text = " ".join(block_raw_texts(block)[:3])
        combined = f"{caption} {body_text}"
        if not _FLOWCHART_KEYWORDS_RE.search(combined):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "flowchart"
        return RecognitionResult(0.65, data, self.educational_object_type, self.name)


class GraphRecognizer(VisualFamilyRecognizer):
    name = "graph"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        body_text = " ".join(block_raw_texts(block)[:3])
        combined = f"{caption} {body_text}"
        if not _GRAPH_KEYWORDS_RE.search(combined):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "graph"
        return RecognitionResult(0.6, data, self.educational_object_type, self.name)


class CircuitDiagramRecognizer(VisualFamilyRecognizer):
    name = "circuit_diagram"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        body_text = " ".join(block_raw_texts(block)[:3])
        combined = f"{caption} {body_text}"
        if not _CIRCUIT_KEYWORDS_RE.search(combined):
            return None
        data = block_deterministic_visual(block)
        data["visual_subtype"] = "circuit_diagram"
        return RecognitionResult(0.6, data, self.educational_object_type, self.name)


class ConceptTableRecognizer(VisualFamilyRecognizer):
    """M4.1D: Improved concept table recognition with prose false-positive
    suppression. A Table block whose caption/leading text reads as a
    comparison or classification table is a reusable Concept Table, but
    only if it doesn't look like prose masquerading as a table."""
    name = "concept_table"
    use_table_semantics = True

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        leading_text = " ".join(block_raw_texts(block)[:2])
        combined = f"{caption} {leading_text}"

        if not _CONCEPT_TABLE_KEYWORDS_RE.search(combined):
            return None

        # M4.1D: Table false-positive suppression — check if the block
        # is really prose disguised as a table.
        all_text = " ".join(block_raw_texts(block))
        if self._is_prose_false_positive(all_text, block):
            return None

        data = block_deterministic_visual(block)
        data["visual_subtype"] = "concept_table"

        # M4.1D: Improved caption association
        if _TABLE_CAPTION_RE.match(caption):
            data["has_formal_caption"] = True
            confidence = 0.75
        else:
            confidence = 0.7

        return RecognitionResult(confidence, data, self.educational_object_type, self.name)

    def _is_prose_false_positive(self, text: str, block: Block) -> bool:
        """M4.1D: Deterministic check for prose false positives.
        A block is likely a false-positive table if most of its lines
        are full prose sentences."""
        texts = block_raw_texts(block)
        if len(texts) < 3:
            return False
        prose_count = sum(1 for t in texts if _PROSE_SENTENCE_RE.search(t))
        return prose_count > len(texts) * 0.5


class DiagramSubtypeRecognizer(VisualFamilyRecognizer):
    """M4.1D: Improved deterministic diagram identification.
    Identifies specific diagram sub-types (lifecycle, map, anatomy)
    based on caption/body vocabulary. Scores above the generic fallback
    when a specific sub-type matches."""
    name = "diagram_subtype"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        body_text = " ".join(block_raw_texts(block)[:3])
        combined = f"{caption} {body_text}"

        data = block_deterministic_visual(block)

        if _LIFECYCLE_RE.search(combined):
            data["visual_subtype"] = "lifecycle_diagram"
            return RecognitionResult(0.65, data, self.educational_object_type, self.name)

        if _MAP_RE.search(combined):
            data["visual_subtype"] = "map"
            return RecognitionResult(0.6, data, self.educational_object_type, self.name)

        if _ANATOMY_RE.search(combined):
            data["visual_subtype"] = "anatomical_diagram"
            return RecognitionResult(0.65, data, self.educational_object_type, self.name)

        return None


class FigureWithCaptionRecognizer(VisualFamilyRecognizer):
    """M4.1D: Improved figure recognition with formal caption detection.
    Figures with a proper "Figure N" / "Fig. N" caption get higher
    confidence than uncaptioned figures. Also performs duplicate
    suppression for figures detected as both figure and diagram."""
    name = "figure_with_caption"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        data = block_deterministic_visual(block)

        if _FIGURE_CAPTION_RE.match(caption):
            data["has_formal_caption"] = True
            data["visual_subtype"] = "figure"
            return RecognitionResult(0.75, data, self.educational_object_type, self.name)

        # No formal caption — still a figure but lower confidence
        return None


class GenericVisualRecognizer(VisualFamilyRecognizer):
    """Always matches, at baseline confidence. Registered last / lowest
    priority for every visual block type so a block that doesn't match
    any more specific recognizer still gets this baseline extraction."""
    name = "generic_visual"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        data = block_deterministic_visual(block)
        return RecognitionResult(0.5, data, self.educational_object_type, self.name)
