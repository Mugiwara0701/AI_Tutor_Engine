"""
modules/relationship_discovery_engine/rules.py — M5.2E: the
deterministic rule table that maps (source_SemanticRole, target_SemanticRole)
pairs to RelationshipType values.

No LLM involvement.  No randomness.  The table is static, versioned,
and fully auditable.

A "rule" is a mapping entry:
    (source_role, target_role) → (RelationshipType, direction, base_weight, rule_key)

base_weight is the initial evidence weight for a role-pair match — it is
then scaled by the source and target anchor confidence values inside
ConfidencePropagator to produce the final RelationshipConfidence.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Optional, Tuple

from modules.semantic_interpretation_engine.enums import SemanticRole
from modules.relationship_discovery_engine.enums import RelationshipDirection, RelationshipType

__all__ = [
    "RelationshipRule",
    "RELATIONSHIP_RULES",
    "lookup_rule",
]


class RelationshipRule(NamedTuple):
    """
    A single relationship discovery rule.

    Attributes:
        relationship_type:  The RelationshipType to assign.
        direction:          Canonical direction of the edge.
        base_weight:        Evidence weight for this rule match (0.0–1.0).
        rule_key:           Stable string identifier for this rule.
    """

    relationship_type: RelationshipType
    direction: RelationshipDirection
    base_weight: float
    rule_key: str


# ---------------------------------------------------------------------------
# Rule table
# Keys: (source_SemanticRole.value, target_SemanticRole.value)
# ---------------------------------------------------------------------------

RELATIONSHIP_RULES: Dict[Tuple[str, str], RelationshipRule] = {

    # -----------------------------------------------------------------------
    # DEFINES family
    # Definition → Concept: the definition DEFINES the concept.
    ("defines_concept", "defines_concept"): RelationshipRule(
        RelationshipType.DEFINES, RelationshipDirection.FORWARD, 0.90, "rule_defines_concept"
    ),

    # -----------------------------------------------------------------------
    # REQUIRES / PREREQUISITE family
    # Any concept role → prerequisite: the concept REQUIRES the prerequisite.
    ("defines_concept", "states_prerequisite"): RelationshipRule(
        RelationshipType.REQUIRES, RelationshipDirection.FORWARD, 0.85, "rule_requires_prerequisite"
    ),
    ("states_learning_objective", "states_prerequisite"): RelationshipRule(
        RelationshipType.REQUIRES, RelationshipDirection.FORWARD, 0.80, "rule_objective_requires_prerequisite"
    ),

    # -----------------------------------------------------------------------
    # ILLUSTRATES family
    # Example → Concept: the example ILLUSTRATES the concept.
    ("exemplifies_concept", "defines_concept"): RelationshipRule(
        RelationshipType.ILLUSTRATES, RelationshipDirection.FORWARD, 0.85, "rule_illustrates_concept"
    ),

    # -----------------------------------------------------------------------
    # EXPLAINS family
    # Visual purpose → Concept: the figure EXPLAINS the concept.
    ("serves_visual_purpose", "defines_concept"): RelationshipRule(
        RelationshipType.EXPLAINS, RelationshipDirection.FORWARD, 0.80, "rule_figure_explains_concept"
    ),
    ("references_concepts_visually", "defines_concept"): RelationshipRule(
        RelationshipType.EXPLAINS, RelationshipDirection.FORWARD, 0.78, "rule_visual_reference_explains"
    ),
    ("fulfills_teaching_function", "defines_concept"): RelationshipRule(
        RelationshipType.EXPLAINS, RelationshipDirection.FORWARD, 0.75, "rule_teaching_function_explains"
    ),

    # -----------------------------------------------------------------------
    # SUPPORTS family
    # Scientific goal → reasoning: experiment SUPPORTS principle.
    ("states_scientific_goal", "frames_reasoning"): RelationshipRule(
        RelationshipType.SUPPORTS, RelationshipDirection.FORWARD, 0.82, "rule_scientific_supports_reasoning"
    ),
    ("directs_observation", "frames_reasoning"): RelationshipRule(
        RelationshipType.SUPPORTS, RelationshipDirection.FORWARD, 0.78, "rule_observation_supports_reasoning"
    ),
    ("states_scientific_goal", "defines_concept"): RelationshipRule(
        RelationshipType.SUPPORTS, RelationshipDirection.FORWARD, 0.75, "rule_scientific_goal_supports_concept"
    ),

    # -----------------------------------------------------------------------
    # IMPLEMENTS family
    # Procedural → strategy: procedure IMPLEMENTS method.
    ("sequences_instruction", "describes_strategy"): RelationshipRule(
        RelationshipType.IMPLEMENTS, RelationshipDirection.FORWARD, 0.82, "rule_sequence_implements_strategy"
    ),
    ("sequences_instruction", "sequences_instruction"): RelationshipRule(
        RelationshipType.SEQUENCES, RelationshipDirection.FORWARD, 0.70, "rule_sequence_to_sequence"
    ),

    # -----------------------------------------------------------------------
    # EVALUATES family
    # Learning objective → concept: assessment EVALUATES the learning objective.
    ("states_learning_objective", "defines_concept"): RelationshipRule(
        RelationshipType.EVALUATES, RelationshipDirection.FORWARD, 0.80, "rule_objective_evaluates_concept"
    ),
    ("states_learning_objective", "states_learning_objective"): RelationshipRule(
        RelationshipType.EVALUATES, RelationshipDirection.FORWARD, 0.75, "rule_objective_to_objective"
    ),

    # -----------------------------------------------------------------------
    # EXTENDS family
    # Transfer opportunity → concept: transfer EXTENDS understanding.
    ("enables_transfer", "defines_concept"): RelationshipRule(
        RelationshipType.EXTENDS, RelationshipDirection.FORWARD, 0.78, "rule_transfer_extends_concept"
    ),
    ("enables_transfer", "describes_strategy"): RelationshipRule(
        RelationshipType.EXTENDS, RelationshipDirection.FORWARD, 0.75, "rule_transfer_extends_strategy"
    ),

    # -----------------------------------------------------------------------
    # CONTRADICTS family
    # Misconception → concept: misconception CONTRADICTS the concept.
    ("surfaces_misconception", "defines_concept"): RelationshipRule(
        RelationshipType.CONTRADICTS, RelationshipDirection.FORWARD, 0.88, "rule_misconception_contradicts_concept"
    ),

    # -----------------------------------------------------------------------
    # CONTEXTUALIZES family
    # Teaching intent → concept: intent CONTEXTUALIZES the concept.
    ("frames_teaching_intent", "defines_concept"): RelationshipRule(
        RelationshipType.CONTEXTUALIZES, RelationshipDirection.FORWARD, 0.75, "rule_teaching_intent_contextualizes"
    ),
    ("frames_reasoning", "defines_concept"): RelationshipRule(
        RelationshipType.CONTEXTUALIZES, RelationshipDirection.FORWARD, 0.72, "rule_reasoning_contextualizes"
    ),

    # -----------------------------------------------------------------------
    # REFERENCES family (visual/tabular to tabular/visual cross-links)
    ("expresses_comparison", "conveys_relationship"): RelationshipRule(
        RelationshipType.REFERENCES, RelationshipDirection.FORWARD, 0.68, "rule_comparison_references_relationship"
    ),
    ("conveys_relationship", "defines_concept"): RelationshipRule(
        RelationshipType.REFERENCES, RelationshipDirection.FORWARD, 0.68, "rule_relationship_references_concept"
    ),
    ("serves_educational_purpose", "defines_concept"): RelationshipRule(
        RelationshipType.REFERENCES, RelationshipDirection.FORWARD, 0.65, "rule_educational_purpose_references"
    ),

    # -----------------------------------------------------------------------
    # SUMMARIZES family
    # Teaching function → full structure.
    ("fulfills_teaching_function", "sequences_instruction"): RelationshipRule(
        RelationshipType.SUMMARIZES, RelationshipDirection.FORWARD, 0.70, "rule_teaching_function_summarizes"
    ),
}


def lookup_rule(
    source_role: str,
    target_role: str,
) -> Optional[RelationshipRule]:
    """
    Look up the RelationshipRule for a (source_role, target_role) pair.

    Both arguments should be SemanticRole.value strings.
    Returns None if no rule matches (caller falls back to RELATED_TO
    with a low weight).
    """
    return RELATIONSHIP_RULES.get((source_role, target_role))
