"""
modules/relationship_discovery_engine/exceptions.py — M5.2E exception
hierarchy for the Relationship Discovery & Semantic Graph Engine.
"""
from __future__ import annotations

__all__ = [
    "RelationshipDiscoveryError",
    "RelationshipResolutionError",
    "RelationshipClassificationError",
    "RelationshipValidationError",
    "ConfidencePropagationError",
    "GraphBuildError",
    "GraphNormalizationError",
    "GraphIntegrityError",
    "GraphExportError",
    "RelationshipDiscoveryEngineError",
]


class RelationshipDiscoveryError(Exception):
    """Base for all M5.2E errors."""


class RelationshipResolutionError(RelationshipDiscoveryError):
    """Raised when candidate relationship pairs cannot be resolved."""


class RelationshipClassificationError(RelationshipDiscoveryError):
    """Raised when a relationship type cannot be classified."""


class RelationshipValidationError(RelationshipDiscoveryError):
    """Raised when relationship validation fails unrecoverably."""


class ConfidencePropagationError(RelationshipDiscoveryError):
    """Raised when confidence cannot be propagated."""


class GraphBuildError(RelationshipDiscoveryError):
    """Raised when the semantic graph cannot be constructed."""


class GraphNormalizationError(RelationshipDiscoveryError):
    """Raised when graph normalization encounters an unrecoverable state."""


class GraphIntegrityError(RelationshipDiscoveryError):
    """Raised when graph integrity validation fails unrecoverably."""


class GraphExportError(RelationshipDiscoveryError):
    """Raised when the graph cannot be serialized or exported."""


class RelationshipDiscoveryEngineError(RelationshipDiscoveryError):
    """Raised by the top-level engine for unexpected failures."""
