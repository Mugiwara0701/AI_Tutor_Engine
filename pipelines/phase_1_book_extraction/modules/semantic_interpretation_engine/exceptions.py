"""
modules/semantic_interpretation_engine/exceptions.py — M5.2D: exception
hierarchy for the Semantic Interpretation & Enrichment Engine.

All exceptions inherit from SemanticInterpretationError so callers can
catch the entire subsystem with a single except clause.  The hierarchy
mirrors the conventions established by M5.1–M5.2C.
"""
from __future__ import annotations

__all__ = [
    "SemanticInterpretationError",
    "SemanticResolutionError",
    "SemanticAnchorError",
    "SemanticEnrichmentError",
    "ConfidenceEvaluationError",
    "CompatibilityInterpretationError",
    "HintDiagnosticsError",
    "PatternVersionError",
    "SemanticValidationError",
]


class SemanticInterpretationError(Exception):
    """Base for all M5.2D errors."""


class SemanticResolutionError(SemanticInterpretationError):
    """Raised when a structural role cannot be mapped to a SemanticRole."""


class SemanticAnchorError(SemanticInterpretationError):
    """Raised when a SemanticAnchor cannot be built or validated."""


class SemanticEnrichmentError(SemanticInterpretationError):
    """Raised when the enrichment pipeline encounters an unrecoverable state."""


class ConfidenceEvaluationError(SemanticInterpretationError):
    """Raised when confidence cannot be computed (e.g. invalid score range)."""


class CompatibilityInterpretationError(SemanticInterpretationError):
    """Raised when the CompatibilityInterpreter cannot produce a result."""


class HintDiagnosticsError(SemanticInterpretationError):
    """Raised when hint diagnostic extraction fails."""


class PatternVersionError(SemanticInterpretationError):
    """Raised when a PatternVersion or PatternVersionRegistry is malformed."""


class SemanticValidationError(SemanticInterpretationError):
    """Raised when a semantic model fails its internal validation contract."""
