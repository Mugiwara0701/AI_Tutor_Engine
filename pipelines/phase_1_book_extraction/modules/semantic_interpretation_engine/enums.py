"""
modules/semantic_interpretation_engine/enums.py — M5.2D: enumerated
vocabularies for the Semantic Interpretation & Enrichment Engine.

All enums are str-based so they serialize naturally to JSON and compare
cleanly against string literals — consistent with the conventions
established by M5.1, M5.2A, M5.2B, and M5.2C.
"""
from __future__ import annotations

from enum import Enum

__all__ = [
    "SemanticRole",
    "PedagogicalRole",
    "LearningIntent",
    "InstructionalContext",
    "ConfidenceLevel",
    "EnrichmentOutcome",
    "CompatibilitySeverity",
]


class SemanticRole(str, Enum):
    """
    The semantic function a structural component plays within its
    educational object.  These roles are pattern-independent: a
    "definition" component in a Worked Example and a "definition"
    component in a standalone Definition object both carry
    DEFINES_CONCEPT.
    """

    # Core knowledge roles
    DEFINES_CONCEPT = "defines_concept"
    EXEMPLIFIES_CONCEPT = "exemplifies_concept"
    STATES_PREREQUISITE = "states_prerequisite"
    SURFACES_MISCONCEPTION = "surfaces_misconception"
    FRAMES_TEACHING_INTENT = "frames_teaching_intent"

    # Problem-solving roles
    STATES_LEARNING_OBJECTIVE = "states_learning_objective"
    DESCRIBES_STRATEGY = "describes_strategy"
    SEQUENCES_INSTRUCTION = "sequences_instruction"
    ENABLES_TRANSFER = "enables_transfer"

    # Scientific / empirical roles
    STATES_SCIENTIFIC_GOAL = "states_scientific_goal"
    DIRECTS_OBSERVATION = "directs_observation"
    FRAMES_REASONING = "frames_reasoning"

    # Visual / tabular roles
    REFERENCES_CONCEPTS_VISUALLY = "references_concepts_visually"
    SERVES_VISUAL_PURPOSE = "serves_visual_purpose"
    FULFILLS_TEACHING_FUNCTION = "fulfills_teaching_function"
    EXPRESSES_COMPARISON = "expresses_comparison"
    CONVEYS_RELATIONSHIP = "conveys_relationship"
    SERVES_EDUCATIONAL_PURPOSE = "serves_educational_purpose"

    # Generic fallback
    UNKNOWN = "unknown"


class PedagogicalRole(str, Enum):
    """
    The broad pedagogical function the entire educational object
    serves in its instructional context.
    """

    INTRODUCE = "introduce"
    REINFORCE = "reinforce"
    ASSESS = "assess"
    EXTEND = "extend"
    REMEDIATE = "remediate"
    UNKNOWN = "unknown"


class LearningIntent(str, Enum):
    """
    The primary learning intent the educational object is designed to
    fulfil.
    """

    DECLARATIVE_KNOWLEDGE = "declarative_knowledge"   # facts, definitions, concepts
    PROCEDURAL_KNOWLEDGE = "procedural_knowledge"     # steps, algorithms, strategies
    CONCEPTUAL_UNDERSTANDING = "conceptual_understanding"
    PROBLEM_SOLVING = "problem_solving"
    SCIENTIFIC_INQUIRY = "scientific_inquiry"
    VISUAL_COMPREHENSION = "visual_comprehension"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    UNKNOWN = "unknown"


class InstructionalContext(str, Enum):
    """
    The instructional setting or pedagogical phase this object
    typically inhabits.
    """

    EXPOSITION = "exposition"          # new material introduction
    ELABORATION = "elaboration"        # deepening understanding
    PRACTICE = "practice"              # application / worked problems
    EVALUATION = "evaluation"          # assessment / self-check
    ENRICHMENT = "enrichment"          # extension / transfer
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """
    Ordinal confidence band for a ConfidenceScore value.
    """

    HIGH = "high"       # score >= 0.80
    MEDIUM = "medium"   # score >= 0.50
    LOW = "low"         # score >= 0.20
    NONE = "none"       # score < 0.20


class EnrichmentOutcome(str, Enum):
    """
    Overall outcome of a SemanticEnrichmentResult.
    """

    COMPLETE = "complete"               # all components interpreted, anchors built
    PARTIAL = "partial"                 # some components interpreted
    UNRECOGNIZED = "unrecognized"       # no matching pattern found
    INCOMPATIBLE = "incompatible"       # taxonomy / version mismatch
    ERROR = "error"                     # internal error during enrichment


class CompatibilitySeverity(str, Enum):
    """
    Severity level for a CompatibilityResult.
    """

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
