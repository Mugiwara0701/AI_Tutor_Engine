"""
modules/semantic_interpretation_engine — M5.2D: the Semantic
Interpretation & Enrichment Engine.

Builds strictly additively on top of three frozen milestones:

- M5.1 (`modules.educational_object_framework`) — reuses
  ValidationResult / ValidationDiagnostic / DiagnosticSeverity / SUCCESS
  directly; never duplicates them.
- M5.2A (`modules.educational_taxonomy`) — reads EducationalObjectType
  via CompatibilityInterpreter; never modifies TaxonomyRegistry.
- M5.2B (`modules.subject_profile_framework`) — reads
  SubjectContribution hint fields via HintDiagnosticsEngine; never
  writes back to SubjectContribution or SubjectProfile.
- M5.2C (`modules.structural_understanding_engine`) — wraps
  StructuralAnalysisResult, CompatibilityValidator, HintResolver, and
  StructuralPattern with semantic layers; modifies none of them.

Out of scope: Relationship Discovery, Knowledge Graph generation,
LLM integration, copyright normalization, Master JSON generation,
graph construction (M5.2E+).

Public API:

    Enums:
        SemanticRole, PedagogicalRole, LearningIntent,
        InstructionalContext, ConfidenceLevel, EnrichmentOutcome,
        CompatibilitySeverity                            — enums.py

    Models:
        ConfidenceEvidence, ConfidenceScore, ConfidenceBreakdown
        SemanticInterpretation, SemanticObject
        CompatibilityResult
        SemanticAnchor
        SemanticEnrichmentResult
        DEFAULT_SEMANTIC_VERSION                         — models.py

    Hint Diagnostics (Deliverable #3):
        HintWarning, HintDiagnosticsResult
        HintDiagnosticsEngine, default_hint_diagnostics_engine
                                                         — hint_diagnostics.py

    Pattern Versioning (Deliverable #4):
        PatternVersion, PatternMetadata, PatternCompatibility,
        PatternSelection, PatternVersionRegistry
        DEFAULT_PATTERN_SEMANTIC_VERSION
        default_pattern_version_registry                 — pattern_versioning.py

    Confidence (Deliverable #1):
        ConfidenceEvaluator, default_confidence_evaluator
                                                         — confidence.py

    Compatibility Reporting (Deliverable #2):
        CompatibilityInterpreter, default_compatibility_interpreter
                                                         — compatibility_interpreter.py

    Semantic Resolution:
        SemanticResolver, default_semantic_resolver, ROLE_MAPPING
                                                         — semantic_resolver.py

    Anchor Builder (Deliverable #5):
        SemanticAnchorBuilder, default_anchor_builder, ANCHOR_NAMESPACE
                                                         — anchor_builder.py

    Engine:
        SemanticInterpretationEngine, SemanticEnrichmentEngine,
        default_engine, enrich                           — engine.py

    Validation:
        validate_semantic_enrichment_result,
        validate_anchor_uniqueness,
        validate_confidence_consistency                  — validation.py

    Config:
        SemanticInterpretationEngineConfig, default_config,
        DEFAULT_ENGINE_VERSION                           — config.py

    Exceptions:
        SemanticInterpretationError and subclasses       — exceptions.py
"""
from __future__ import annotations

# --- Enums ---
from modules.semantic_interpretation_engine.enums import (
    CompatibilitySeverity,
    ConfidenceLevel,
    EnrichmentOutcome,
    InstructionalContext,
    LearningIntent,
    PedagogicalRole,
    SemanticRole,
)

# --- Models ---
from modules.semantic_interpretation_engine.models import (
    DEFAULT_SEMANTIC_VERSION,
    CompatibilityResult,
    ConfidenceBreakdown,
    ConfidenceEvidence,
    ConfidenceScore,
    SemanticAnchor,
    SemanticEnrichmentResult,
    SemanticInterpretation,
    SemanticObject,
)

# --- Config ---
from modules.semantic_interpretation_engine.config import (
    DEFAULT_ENGINE_VERSION,
    SemanticInterpretationEngineConfig,
    default_config,
)

# --- Exceptions ---
from modules.semantic_interpretation_engine.exceptions import (
    CompatibilityInterpretationError,
    ConfidenceEvaluationError,
    HintDiagnosticsError,
    PatternVersionError,
    SemanticAnchorError,
    SemanticEnrichmentError,
    SemanticInterpretationError,
    SemanticResolutionError,
    SemanticValidationError,
)

# --- Hint Diagnostics (Deliverable #3) ---
from modules.semantic_interpretation_engine.hint_diagnostics import (
    HintDiagnosticsEngine,
    HintDiagnosticsResult,
    HintWarning,
    default_hint_diagnostics_engine,
)

# --- Pattern Versioning (Deliverable #4) ---
from modules.semantic_interpretation_engine.pattern_versioning import (
    DEFAULT_PATTERN_SEMANTIC_VERSION,
    PatternCompatibility,
    PatternMetadata,
    PatternSelection,
    PatternVersion,
    PatternVersionRegistry,
    default_pattern_version_registry,
)

# --- Confidence (Deliverable #1) ---
from modules.semantic_interpretation_engine.confidence import (
    ConfidenceEvaluator,
    default_confidence_evaluator,
)

# --- Compatibility Reporting (Deliverable #2) ---
from modules.semantic_interpretation_engine.compatibility_interpreter import (
    CompatibilityInterpreter,
    default_compatibility_interpreter,
)

# --- Semantic Resolution ---
from modules.semantic_interpretation_engine.semantic_resolver import (
    ROLE_MAPPING,
    SemanticResolver,
    default_semantic_resolver,
)

# --- Anchor Builder (Deliverable #5) ---
from modules.semantic_interpretation_engine.anchor_builder import (
    ANCHOR_NAMESPACE,
    SemanticAnchorBuilder,
    default_anchor_builder,
)

# --- Engine ---
from modules.semantic_interpretation_engine.engine import (
    SemanticEnrichmentEngine,
    SemanticInterpretationEngine,
    default_engine,
    enrich,
)

# --- Validation ---
from modules.semantic_interpretation_engine.validation import (
    validate_anchor_uniqueness,
    validate_confidence_consistency,
    validate_semantic_enrichment_result,
)

__all__ = [
    # enums
    "SemanticRole",
    "PedagogicalRole",
    "LearningIntent",
    "InstructionalContext",
    "ConfidenceLevel",
    "EnrichmentOutcome",
    "CompatibilitySeverity",
    # models
    "ConfidenceEvidence",
    "ConfidenceScore",
    "ConfidenceBreakdown",
    "SemanticInterpretation",
    "SemanticObject",
    "CompatibilityResult",
    "SemanticAnchor",
    "SemanticEnrichmentResult",
    "DEFAULT_SEMANTIC_VERSION",
    # config
    "SemanticInterpretationEngineConfig",
    "default_config",
    "DEFAULT_ENGINE_VERSION",
    # exceptions
    "SemanticInterpretationError",
    "SemanticResolutionError",
    "SemanticAnchorError",
    "SemanticEnrichmentError",
    "ConfidenceEvaluationError",
    "CompatibilityInterpretationError",
    "HintDiagnosticsError",
    "PatternVersionError",
    "SemanticValidationError",
    # hint diagnostics (Deliverable #3)
    "HintWarning",
    "HintDiagnosticsResult",
    "HintDiagnosticsEngine",
    "default_hint_diagnostics_engine",
    # pattern versioning (Deliverable #4)
    "PatternVersion",
    "PatternMetadata",
    "PatternCompatibility",
    "PatternSelection",
    "PatternVersionRegistry",
    "DEFAULT_PATTERN_SEMANTIC_VERSION",
    "default_pattern_version_registry",
    # confidence (Deliverable #1)
    "ConfidenceEvaluator",
    "default_confidence_evaluator",
    # compatibility reporting (Deliverable #2)
    "CompatibilityInterpreter",
    "default_compatibility_interpreter",
    # semantic resolution
    "SemanticResolver",
    "default_semantic_resolver",
    "ROLE_MAPPING",
    # anchor builder (Deliverable #5)
    "SemanticAnchorBuilder",
    "default_anchor_builder",
    "ANCHOR_NAMESPACE",
    # engine
    "SemanticInterpretationEngine",
    "SemanticEnrichmentEngine",
    "default_engine",
    "enrich",
    # validation
    "validate_semantic_enrichment_result",
    "validate_anchor_uniqueness",
    "validate_confidence_consistency",
]
