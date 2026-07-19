"""
modules/semantic_interpretation_engine/engine.py — M5.2D:
SemanticInterpretationEngine and SemanticEnrichmentEngine.

The engine is the central coordinator.  It:
1. Accepts a M5.2C StructuralAnalysisResult (wrapped by value — no
   live M5.2C type reference escapes M5.2D's public surface).
2. Resolves structural roles → semantic interpretations via SemanticResolver.
3. Computes confidence via ConfidenceEvaluator.
4. Interprets compatibility via CompatibilityInterpreter.
5. Builds a SemanticAnchor via SemanticAnchorBuilder.
6. Returns a SemanticEnrichmentResult.

Nothing in M5.2C is modified.  The engine only consumes M5.2C outputs.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from modules.structural_understanding_engine.enums import AnalysisOutcome
from modules.structural_understanding_engine.structural_models import (
    StructuralAnalysisResult,
    StructuralObject,
)

from modules.semantic_interpretation_engine.anchor_builder import (
    SemanticAnchorBuilder,
    default_anchor_builder,
)
from modules.semantic_interpretation_engine.compatibility_interpreter import (
    CompatibilityInterpreter,
    default_compatibility_interpreter,
)
from modules.semantic_interpretation_engine.confidence import (
    ConfidenceEvaluator,
    default_confidence_evaluator,
)
from modules.semantic_interpretation_engine.config import (
    SemanticInterpretationEngineConfig,
    default_config,
)
from modules.semantic_interpretation_engine.enums import (
    EnrichmentOutcome,
    InstructionalContext,
    LearningIntent,
    PedagogicalRole,
    SemanticRole,
)
from modules.semantic_interpretation_engine.exceptions import SemanticEnrichmentError
from modules.semantic_interpretation_engine.models import (
    CompatibilityResult,
    ConfidenceBreakdown,
    ConfidenceEvidence,
    ConfidenceScore,
    ConfidenceLevel,
    SemanticAnchor,
    SemanticEnrichmentResult,
    SemanticInterpretation,
    SemanticObject,
)
from modules.semantic_interpretation_engine.semantic_resolver import (
    SemanticResolver,
    default_semantic_resolver,
)
from modules.semantic_interpretation_engine.enums import CompatibilitySeverity

__all__ = [
    "SemanticInterpretationEngine",
    "SemanticEnrichmentEngine",
    "default_engine",
    "enrich",
]

_ZERO_SCORE = ConfidenceScore(
    value=0.0,
    level=ConfidenceLevel.NONE,
    evidence=(
        ConfidenceEvidence(label="not_applicable", weight=1.0, passed=False, detail=""),
    ),
)
_ZERO_BREAKDOWN = ConfidenceBreakdown(
    structural=_ZERO_SCORE,
    semantic=_ZERO_SCORE,
    enrichment=_ZERO_SCORE,
)
_ZERO_COMPAT = CompatibilityResult(
    compatible=False,
    severity=CompatibilitySeverity.WARNING,
    reason="Compatibility check was not performed.",
    suggested_resolution="Provide an object_type to enable compatibility checking.",
)


class SemanticInterpretationEngine:
    """
    Interprets a single StructuralAnalysisResult into a SemanticObject.

    This is the inner engine: given a structural result and (optionally)
    an EducationalObjectType, produce the semantic layer.
    """

    def __init__(
        self,
        resolver: Optional[SemanticResolver] = None,
        config: Optional[SemanticInterpretationEngineConfig] = None,
    ) -> None:
        self._resolver = resolver or default_semantic_resolver
        self._cfg = config or default_config

    def interpret(
        self,
        structural_result: StructuralAnalysisResult,
        structural_object: Optional[StructuralObject] = None,
    ) -> Optional[SemanticObject]:
        """
        Produce a SemanticObject from *structural_result*.

        Returns None if the outcome is UNRECOGNIZED or ERROR.
        """
        if structural_result.outcome == AnalysisOutcome.UNRECOGNIZED_PATTERN:
            return None

        roles: List[str] = list(structural_result.present_roles)
        interpretations = self._resolver.resolve_all(roles)

        # Determine dominant intents from interpretations
        dominant = self._dominant_tuple(interpretations)

        return SemanticObject(
            object_key=structural_result.object_key,
            object_type_key=(
                structural_object.object_type_key
                if structural_object is not None
                else ""
            ),
            pattern_key=structural_result.pattern_key,
            interpretations=tuple(interpretations),
            pedagogical_role=dominant[0],
            learning_intent=dominant[1],
            instructional_context=dominant[2],
        )

    @staticmethod
    def _dominant_tuple(
        interpretations: List[SemanticInterpretation],
    ) -> Tuple[PedagogicalRole, LearningIntent, InstructionalContext]:
        """Pick the dominant (ped_role, intent, context) by highest confidence."""
        if not interpretations:
            return (
                PedagogicalRole.UNKNOWN,
                LearningIntent.UNKNOWN,
                InstructionalContext.UNKNOWN,
            )
        best = max(interpretations, key=lambda i: i.confidence.value)
        return best.pedagogical_role, best.learning_intent, best.instructional_context


class SemanticEnrichmentEngine:
    """
    The outer engine that coordinates all M5.2D deliverables and produces
    a SemanticEnrichmentResult.

    Usage:
        engine = SemanticEnrichmentEngine()
        result = engine.enrich(structural_result, structural_object, object_type)
    """

    def __init__(
        self,
        interpretation_engine: Optional[SemanticInterpretationEngine] = None,
        confidence_evaluator: Optional[ConfidenceEvaluator] = None,
        compatibility_interpreter: Optional[CompatibilityInterpreter] = None,
        anchor_builder: Optional[SemanticAnchorBuilder] = None,
        config: Optional[SemanticInterpretationEngineConfig] = None,
    ) -> None:
        self._interp = interpretation_engine or SemanticInterpretationEngine()
        self._confidence = confidence_evaluator or default_confidence_evaluator
        self._compat = compatibility_interpreter or default_compatibility_interpreter
        self._anchor = anchor_builder or default_anchor_builder
        self._cfg = config or default_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(
        self,
        structural_result: StructuralAnalysisResult,
        structural_object: Optional[StructuralObject] = None,
        object_type: Optional[object] = None,
    ) -> SemanticEnrichmentResult:
        """
        Produce a SemanticEnrichmentResult wrapping *structural_result*.

        Parameters
        ----------
        structural_result:
            Output of M5.2C's StructuralUnderstandingEngine.analyze().
        structural_object:
            The StructuralObject that was analysed (optional; provides
            object_type_key for SemanticObject).
        object_type:
            An EducationalObjectType from M5.2A (optional; enables
            CompatibilityInterpreter to produce a rich result).
        """
        diagnostics: List[str] = []
        try:
            return self._run_enrichment(
                structural_result=structural_result,
                structural_object=structural_object,
                object_type=object_type,
                diagnostics=diagnostics,
            )
        except SemanticEnrichmentError:
            raise
        except Exception as exc:
            raise SemanticEnrichmentError(
                f"Unexpected error during semantic enrichment for "
                f"object_key={structural_result.object_key!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_enrichment(
        self,
        structural_result: StructuralAnalysisResult,
        structural_object: Optional[StructuralObject],
        object_type: Optional[object],
        diagnostics: List[str],
    ) -> SemanticEnrichmentResult:

        # 1. Compatibility check (Deliverable #2)
        compat_result = self._check_compatibility(object_type, diagnostics)

        # 2. Semantic interpretation
        semantic_object = self._interp.interpret(structural_result, structural_object)
        if semantic_object is None:
            diagnostics.append(
                f"SemanticInterpretationEngine returned no result for "
                f"outcome={structural_result.outcome.value!r}."
            )

        # 3. Confidence evaluation (Deliverable #1)
        interpretation_count = (
            len(semantic_object.interpretations) if semantic_object else 0
        )
        has_anchor_placeholder = semantic_object is not None  # anchor built in step 4
        confidence = self._confidence.evaluate(
            analysis_outcome=structural_result.outcome,
            present_roles=structural_result.present_roles,
            missing_roles=structural_result.missing_roles,
            pattern_key=structural_result.pattern_key,
            interpretation_count=interpretation_count,
            has_anchor=has_anchor_placeholder,
        )

        # 4. Semantic anchor (Deliverable #5)
        anchor: Optional[SemanticAnchor] = None
        if semantic_object is not None:
            try:
                anchor = self._anchor.build(semantic_object, engine_version=self._cfg.version)
            except Exception as exc:
                diagnostics.append(f"SemanticAnchorBuilder failed: {exc}")

        # 5. Outcome determination
        outcome = self._determine_outcome(
            structural_result=structural_result,
            semantic_object=semantic_object,
            compat_result=compat_result,
        )

        # 6. Structural snapshot (frozen dict copy of M5.2C result)
        structural_snapshot = structural_result.to_dict()

        return SemanticEnrichmentResult(
            object_key=structural_result.object_key,
            outcome=outcome,
            semantic_object=semantic_object,
            confidence=confidence,
            compatibility_result=compat_result,
            anchor=anchor,
            structural_snapshot=structural_snapshot,
            diagnostics=tuple(diagnostics),
            version=self._cfg.version,
        )

    def _check_compatibility(
        self,
        object_type: Optional[object],
        diagnostics: List[str],
    ) -> CompatibilityResult:
        if object_type is None:
            return _ZERO_COMPAT
        try:
            return self._compat.interpret_object_type(object_type)
        except Exception as exc:
            diagnostics.append(f"CompatibilityInterpreter failed: {exc}")
            return CompatibilityResult(
                compatible=False,
                severity=CompatibilitySeverity.ERROR,
                reason=f"Compatibility check raised an error: {exc}",
                suggested_resolution="Inspect CompatibilityInterpreter configuration.",
            )

    @staticmethod
    def _determine_outcome(
        *,
        structural_result: StructuralAnalysisResult,
        semantic_object: Optional[SemanticObject],
        compat_result: CompatibilityResult,
    ) -> EnrichmentOutcome:
        if not compat_result.compatible and compat_result.severity == CompatibilitySeverity.ERROR:
            return EnrichmentOutcome.INCOMPATIBLE
        if structural_result.outcome == AnalysisOutcome.UNRECOGNIZED_PATTERN:
            return EnrichmentOutcome.UNRECOGNIZED
        if semantic_object is None:
            return EnrichmentOutcome.ERROR
        if structural_result.outcome == AnalysisOutcome.COMPLETE and structural_result.missing_roles == ():
            return EnrichmentOutcome.COMPLETE
        return EnrichmentOutcome.PARTIAL


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

#: Module-level singleton engine.
default_engine = SemanticEnrichmentEngine()


def enrich(
    structural_result: StructuralAnalysisResult,
    structural_object: Optional[StructuralObject] = None,
    object_type: Optional[object] = None,
) -> SemanticEnrichmentResult:
    """Convenience function: enrich via the module-level default engine."""
    return default_engine.enrich(
        structural_result=structural_result,
        structural_object=structural_object,
        object_type=object_type,
    )
