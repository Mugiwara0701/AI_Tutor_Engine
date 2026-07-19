"""
modules/semantic_interpretation_engine/semantic_resolver.py — M5.2D:
maps M5.2C structural roles to M5.2D semantic interpretations.

The mapping is deterministic and pattern-based.  Each StructuralPattern's
component roles are mapped to (SemanticRole, PedagogicalRole,
LearningIntent, InstructionalContext) tuples via a static lookup table.
Unknown roles receive safe UNKNOWN defaults and a LOW confidence score.

No LLM involvement.  No randomness.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from modules.structural_understanding_engine.patterns import StructuralPattern

from modules.semantic_interpretation_engine.config import (
    SemanticInterpretationEngineConfig,
    default_config,
)
from modules.semantic_interpretation_engine.enums import (
    ConfidenceLevel,
    InstructionalContext,
    LearningIntent,
    PedagogicalRole,
    SemanticRole,
)
from modules.semantic_interpretation_engine.models import (
    ConfidenceEvidence,
    ConfidenceScore,
    SemanticInterpretation,
)

__all__ = [
    "SemanticResolver",
    "default_semantic_resolver",
    "ROLE_MAPPING",
]

# ---------------------------------------------------------------------------
# Role mapping table
# ---------------------------------------------------------------------------
# Maps structural role names (lower-cased) to
# (SemanticRole, PedagogicalRole, LearningIntent, InstructionalContext, confidence_boost)
# confidence_boost: extra weight added when the role is an exact known hit (+0.15)
# ---------------------------------------------------------------------------

_RoleMapping = Tuple[SemanticRole, PedagogicalRole, LearningIntent, InstructionalContext]

ROLE_MAPPING: Dict[str, _RoleMapping] = {
    # --- Definition pattern roles ---
    "concept": (
        SemanticRole.DEFINES_CONCEPT,
        PedagogicalRole.INTRODUCE,
        LearningIntent.DECLARATIVE_KNOWLEDGE,
        InstructionalContext.EXPOSITION,
    ),
    "definition": (
        SemanticRole.DEFINES_CONCEPT,
        PedagogicalRole.INTRODUCE,
        LearningIntent.DECLARATIVE_KNOWLEDGE,
        InstructionalContext.EXPOSITION,
    ),
    "prerequisites": (
        SemanticRole.STATES_PREREQUISITE,
        PedagogicalRole.INTRODUCE,
        LearningIntent.DECLARATIVE_KNOWLEDGE,
        InstructionalContext.EXPOSITION,
    ),
    "teaching_intent": (
        SemanticRole.FRAMES_TEACHING_INTENT,
        PedagogicalRole.INTRODUCE,
        LearningIntent.CONCEPTUAL_UNDERSTANDING,
        InstructionalContext.EXPOSITION,
    ),
    "misconceptions": (
        SemanticRole.SURFACES_MISCONCEPTION,
        PedagogicalRole.REMEDIATE,
        LearningIntent.CONCEPTUAL_UNDERSTANDING,
        InstructionalContext.ELABORATION,
    ),
    "examples": (
        SemanticRole.EXEMPLIFIES_CONCEPT,
        PedagogicalRole.REINFORCE,
        LearningIntent.CONCEPTUAL_UNDERSTANDING,
        InstructionalContext.ELABORATION,
    ),

    # --- Worked Example pattern roles ---
    "learning_objective": (
        SemanticRole.STATES_LEARNING_OBJECTIVE,
        PedagogicalRole.INTRODUCE,
        LearningIntent.PROBLEM_SOLVING,
        InstructionalContext.EXPOSITION,
    ),
    "problem_solving_strategy": (
        SemanticRole.DESCRIBES_STRATEGY,
        PedagogicalRole.REINFORCE,
        LearningIntent.PROCEDURAL_KNOWLEDGE,
        InstructionalContext.PRACTICE,
    ),
    "instructional_progression": (
        SemanticRole.SEQUENCES_INSTRUCTION,
        PedagogicalRole.REINFORCE,
        LearningIntent.PROCEDURAL_KNOWLEDGE,
        InstructionalContext.PRACTICE,
    ),
    "transfer_opportunities": (
        SemanticRole.ENABLES_TRANSFER,
        PedagogicalRole.EXTEND,
        LearningIntent.PROBLEM_SOLVING,
        InstructionalContext.ENRICHMENT,
    ),
    "steps": (
        SemanticRole.SEQUENCES_INSTRUCTION,
        PedagogicalRole.REINFORCE,
        LearningIntent.PROCEDURAL_KNOWLEDGE,
        InstructionalContext.PRACTICE,
    ),
    "solution": (
        SemanticRole.DESCRIBES_STRATEGY,
        PedagogicalRole.REINFORCE,
        LearningIntent.PROBLEM_SOLVING,
        InstructionalContext.PRACTICE,
    ),

    # --- Experiment pattern roles ---
    "scientific_goal": (
        SemanticRole.STATES_SCIENTIFIC_GOAL,
        PedagogicalRole.INTRODUCE,
        LearningIntent.SCIENTIFIC_INQUIRY,
        InstructionalContext.EXPOSITION,
    ),
    "observation_intent": (
        SemanticRole.DIRECTS_OBSERVATION,
        PedagogicalRole.REINFORCE,
        LearningIntent.SCIENTIFIC_INQUIRY,
        InstructionalContext.PRACTICE,
    ),
    "reasoning_objective": (
        SemanticRole.FRAMES_REASONING,
        PedagogicalRole.EXTEND,
        LearningIntent.SCIENTIFIC_INQUIRY,
        InstructionalContext.ELABORATION,
    ),
    "materials": (
        SemanticRole.DIRECTS_OBSERVATION,
        PedagogicalRole.REINFORCE,
        LearningIntent.SCIENTIFIC_INQUIRY,
        InstructionalContext.PRACTICE,
    ),
    "procedure": (
        SemanticRole.SEQUENCES_INSTRUCTION,
        PedagogicalRole.REINFORCE,
        LearningIntent.PROCEDURAL_KNOWLEDGE,
        InstructionalContext.PRACTICE,
    ),
    "observations": (
        SemanticRole.DIRECTS_OBSERVATION,
        PedagogicalRole.REINFORCE,
        LearningIntent.SCIENTIFIC_INQUIRY,
        InstructionalContext.PRACTICE,
    ),

    # --- Figure pattern roles ---
    "referenced_concepts": (
        SemanticRole.REFERENCES_CONCEPTS_VISUALLY,
        PedagogicalRole.REINFORCE,
        LearningIntent.VISUAL_COMPREHENSION,
        InstructionalContext.ELABORATION,
    ),
    "visual_purpose": (
        SemanticRole.SERVES_VISUAL_PURPOSE,
        PedagogicalRole.REINFORCE,
        LearningIntent.VISUAL_COMPREHENSION,
        InstructionalContext.ELABORATION,
    ),
    "teaching_function": (
        SemanticRole.FULFILLS_TEACHING_FUNCTION,
        PedagogicalRole.REINFORCE,
        LearningIntent.VISUAL_COMPREHENSION,
        InstructionalContext.ELABORATION,
    ),
    "caption": (
        SemanticRole.SERVES_VISUAL_PURPOSE,
        PedagogicalRole.REINFORCE,
        LearningIntent.VISUAL_COMPREHENSION,
        InstructionalContext.ELABORATION,
    ),
    "image": (
        SemanticRole.REFERENCES_CONCEPTS_VISUALLY,
        PedagogicalRole.REINFORCE,
        LearningIntent.VISUAL_COMPREHENSION,
        InstructionalContext.ELABORATION,
    ),

    # --- Table pattern roles ---
    "comparison_intent": (
        SemanticRole.EXPRESSES_COMPARISON,
        PedagogicalRole.REINFORCE,
        LearningIntent.COMPARATIVE_ANALYSIS,
        InstructionalContext.ELABORATION,
    ),
    "relationship_meaning": (
        SemanticRole.CONVEYS_RELATIONSHIP,
        PedagogicalRole.REINFORCE,
        LearningIntent.COMPARATIVE_ANALYSIS,
        InstructionalContext.ELABORATION,
    ),
    "educational_purpose": (
        SemanticRole.SERVES_EDUCATIONAL_PURPOSE,
        PedagogicalRole.REINFORCE,
        LearningIntent.COMPARATIVE_ANALYSIS,
        InstructionalContext.ELABORATION,
    ),
    "headers": (
        SemanticRole.EXPRESSES_COMPARISON,
        PedagogicalRole.REINFORCE,
        LearningIntent.COMPARATIVE_ANALYSIS,
        InstructionalContext.ELABORATION,
    ),
    "rows": (
        SemanticRole.CONVEYS_RELATIONSHIP,
        PedagogicalRole.REINFORCE,
        LearningIntent.COMPARATIVE_ANALYSIS,
        InstructionalContext.ELABORATION,
    ),
}

_UNKNOWN_MAPPING: _RoleMapping = (
    SemanticRole.UNKNOWN,
    PedagogicalRole.UNKNOWN,
    LearningIntent.UNKNOWN,
    InstructionalContext.UNKNOWN,
)


class SemanticResolver:
    """
    Deterministically maps structural component roles to
    SemanticInterpretation entries.
    """

    def __init__(self, config: Optional[SemanticInterpretationEngineConfig] = None) -> None:
        self._cfg = config or default_config

    def resolve_role(
        self,
        structural_role: str,
        pattern: Optional[StructuralPattern] = None,
    ) -> SemanticInterpretation:
        """
        Produce a SemanticInterpretation for a single structural role.
        """
        key = structural_role.lower().strip()
        mapping = ROLE_MAPPING.get(key)

        if mapping is not None:
            sem_role, ped_role, intent, context = mapping
            evidence = [
                ConfidenceEvidence(
                    label="exact_role_match",
                    weight=0.70,
                    passed=True,
                    detail=f"structural_role={structural_role!r} → SemanticRole={sem_role.value}",
                ),
                ConfidenceEvidence(
                    label="pattern_provided",
                    weight=0.30,
                    passed=pattern is not None,
                    detail=f"pattern_key={getattr(pattern, 'pattern_key', None)!r}",
                ),
            ]
            raw_score = sum(e.weight for e in evidence if e.passed) / sum(e.weight for e in evidence)
            score = round(raw_score, 4)
        else:
            # Unknown role — safe defaults, low confidence
            sem_role, ped_role, intent, context = _UNKNOWN_MAPPING
            evidence = [
                ConfidenceEvidence(
                    label="exact_role_match",
                    weight=0.70,
                    passed=False,
                    detail=f"structural_role={structural_role!r} not in ROLE_MAPPING",
                ),
                ConfidenceEvidence(
                    label="pattern_provided",
                    weight=0.30,
                    passed=pattern is not None,
                    detail=f"pattern_key={getattr(pattern, 'pattern_key', None)!r}",
                ),
            ]
            raw_score = sum(e.weight for e in evidence if e.passed) / sum(e.weight for e in evidence)
            score = round(raw_score, 4)

        level = (
            ConfidenceLevel.HIGH if score >= self._cfg.high_confidence_threshold
            else ConfidenceLevel.MEDIUM if score >= self._cfg.medium_confidence_threshold
            else ConfidenceLevel.LOW if score >= self._cfg.low_confidence_threshold
            else ConfidenceLevel.NONE
        )

        confidence = ConfidenceScore(value=score, level=level, evidence=tuple(evidence))

        return SemanticInterpretation(
            structural_role=structural_role,
            semantic_role=sem_role,
            pedagogical_role=ped_role,
            learning_intent=intent,
            instructional_context=context,
            confidence=confidence,
        )

    def resolve_all(
        self,
        roles: List[str],
        pattern: Optional[StructuralPattern] = None,
    ) -> List[SemanticInterpretation]:
        """
        Resolve all roles, returning a list ordered by structural_role
        (deterministic).
        """
        return [self.resolve_role(r, pattern=pattern) for r in sorted(set(roles))]


#: Module-level singleton.
default_semantic_resolver = SemanticResolver()
