"""
modules/structural_understanding_engine — M5.2C: the Structural
Understanding Engine.

Understands the internal STRUCTURE of educational objects (Worked
Example, Experiment, Proof, Derivation, Definition, Figure, Table, ...)
built strictly additively on top of three frozen milestones:

- M5.1 (`modules.educational_object_framework`) — reuses
  `ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
  directly; never duplicates them.
- M5.2A (`modules.educational_taxonomy`) — wraps `EducationalObjectType`
  / `TaxonomyRegistry` via `compatibility.py`; never modifies either.
- M5.2B (`modules.subject_profile_framework`) — resolves
  `SubjectContribution`'s raw `Mapping[str, Any]` hint fields into
  typed M5.2C models via `hint_resolver.HintResolver`; never writes
  back into `SubjectContribution`, and never modifies `SubjectProfile`
  / `SubjectProfileRegistry` (their lifecycle is tracked externally by
  `lifecycle.ProfileActivationManager`).

Out of scope (see README.md for the full list): semantic enrichment,
relationship discovery, knowledge graph integration, DST integration,
copyright normalization, Master JSON generation, LLM integration.

Public API:
    ProcessingHints, RecognitionHints, StructuralHints, ValidationHints,
    RelationshipHints, ResolvedHints                       — hints.py
    HintResolver, default_resolver, resolve                — hint_resolver.py
    StructuralComponent, StructuralPattern,
    StructuralPatternRegistry, default_structural_patterns,
    register, unregister, get, all_patterns                — patterns.py
    StructuralObject, StructuralAnalysisResult              — structural_models.py
    TaxonomyCompatibility, DEFAULT_COMPATIBILITY,
    CompatibilityValidator                                  — compatibility.py
    ProfileLifecycleRecord, ProfileActivationManager         — lifecycle.py
    StructuralUnderstandingEngine, default_engine, analyze  — engine.py
    validate_structural_pattern_registry                     — validation.py
    ProfileLifecycleState, CompatibilityOutcome,
    AnalysisOutcome                                          — enums.py
    StructuralUnderstandingEngineConfig, default_config      — config.py
    StructuralUnderstandingEngineError and subclasses        — exceptions.py
"""
from modules.structural_understanding_engine.compatibility import (
    DEFAULT_COMPATIBILITY,
    CompatibilityValidator,
    TaxonomyCompatibility,
)
from modules.structural_understanding_engine.config import (
    StructuralUnderstandingEngineConfig,
    default_config,
)
from modules.structural_understanding_engine.engine import (
    StructuralUnderstandingEngine,
    analyze,
    default_engine,
)
from modules.structural_understanding_engine.enums import (
    AnalysisOutcome,
    CompatibilityOutcome,
    ProfileLifecycleState,
)
from modules.structural_understanding_engine.exceptions import (
    HintResolutionError,
    ProfileLifecycleError,
    StructuralAnalysisError,
    StructuralPatternError,
    StructuralUnderstandingEngineError,
    TaxonomyCompatibilityError,
)
from modules.structural_understanding_engine.hint_resolver import (
    HintResolver,
    default_resolver,
    resolve,
)
from modules.structural_understanding_engine.hints import (
    ProcessingHints,
    RecognitionHints,
    RelationshipHints,
    ResolvedHints,
    StructuralHints,
    ValidationHints,
)
from modules.structural_understanding_engine.lifecycle import (
    ProfileActivationManager,
    ProfileLifecycleRecord,
)
from modules.structural_understanding_engine.patterns import (
    StructuralComponent,
    StructuralPattern,
    StructuralPatternRegistry,
    all_patterns,
    default_structural_patterns,
)
from modules.structural_understanding_engine.patterns import get as get_pattern
from modules.structural_understanding_engine.patterns import register as register_pattern
from modules.structural_understanding_engine.patterns import unregister as unregister_pattern
from modules.structural_understanding_engine.structural_models import (
    StructuralAnalysisResult,
    StructuralObject,
)
from modules.structural_understanding_engine.validation import (
    validate_structural_pattern_registry,
)

__all__ = [
    # hints
    "ProcessingHints",
    "RecognitionHints",
    "StructuralHints",
    "ValidationHints",
    "RelationshipHints",
    "ResolvedHints",
    # hint resolver
    "HintResolver",
    "default_resolver",
    "resolve",
    # patterns
    "StructuralComponent",
    "StructuralPattern",
    "StructuralPatternRegistry",
    "default_structural_patterns",
    "register_pattern",
    "unregister_pattern",
    "get_pattern",
    "all_patterns",
    # structural models
    "StructuralObject",
    "StructuralAnalysisResult",
    # compatibility
    "TaxonomyCompatibility",
    "DEFAULT_COMPATIBILITY",
    "CompatibilityValidator",
    # lifecycle
    "ProfileLifecycleRecord",
    "ProfileActivationManager",
    # engine
    "StructuralUnderstandingEngine",
    "default_engine",
    "analyze",
    # validation
    "validate_structural_pattern_registry",
    # enums
    "ProfileLifecycleState",
    "CompatibilityOutcome",
    "AnalysisOutcome",
    # config
    "StructuralUnderstandingEngineConfig",
    "default_config",
    # exceptions
    "StructuralUnderstandingEngineError",
    "HintResolutionError",
    "StructuralPatternError",
    "StructuralAnalysisError",
    "TaxonomyCompatibilityError",
    "ProfileLifecycleError",
]
