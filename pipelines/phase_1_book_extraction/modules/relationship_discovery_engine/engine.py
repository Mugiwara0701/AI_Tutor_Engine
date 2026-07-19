"""
modules/relationship_discovery_engine/engine.py — M5.2E: the
RelationshipDiscoveryEngine — top-level coordinator.

Consumes SemanticEnrichmentResult objects from M5.2D and produces a
canonical, validated SemanticGraph ready for M5.3.

Pipeline:
  1. RelationshipResolver   → candidate (source, target) pairs
  2. RelationshipClassifier → RelationshipType + rule per pair
  3. ConfidencePropagator   → RelationshipConfidence per relationship
  4. RelationshipBuilder    → SemanticRelationship (frozen)
  5. RelationshipValidator  → per-relationship + list validation
  6. SemanticGraphBuilder   → SemanticGraph (nodes + edges)
  7. GraphNormalizer        → deduplicated, canonical graph
  8. GraphIntegrityValidator→ graph-wide integrity report
  9. GraphExporter          → GraphExportArtifact (for M5.3)

Nothing in M5.2D is modified.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.confidence_propagator import (
    ConfidencePropagator,
    default_confidence_propagator,
)
from modules.relationship_discovery_engine.enums import DiscoveryOutcome, GraphExportFormat
from modules.relationship_discovery_engine.exceptions import RelationshipDiscoveryEngineError
from modules.relationship_discovery_engine.graph_builder import (
    SemanticGraphBuilder,
    default_graph_builder,
)
from modules.relationship_discovery_engine.graph_exporter import (
    GraphExportArtifact,
    GraphExporter,
    default_graph_exporter,
)
from modules.relationship_discovery_engine.graph_integrity_validator import (
    GraphIntegrityValidator,
    default_graph_integrity_validator,
)
from modules.relationship_discovery_engine.graph_normalizer import (
    GraphNormalizer,
    default_graph_normalizer,
)
from modules.relationship_discovery_engine.models import (
    RelationshipDiscoveryResult,
    SemanticGraph,
    SemanticRelationship,
)
from modules.relationship_discovery_engine.relationship_builder import (
    RelationshipBuilder,
    default_relationship_builder,
)
from modules.relationship_discovery_engine.relationship_classifier import (
    RelationshipClassifier,
    default_relationship_classifier,
)
from modules.relationship_discovery_engine.relationship_resolver import (
    RelationshipResolver,
    default_relationship_resolver,
)
from modules.relationship_discovery_engine.relationship_validator import (
    RelationshipValidator,
    default_relationship_validator,
)

__all__ = [
    "RelationshipDiscoveryEngine",
    "default_engine",
    "discover",
]


class RelationshipDiscoveryEngine:
    """
    Top-level coordinator for M5.2E: Relationship Discovery & Semantic
    Graph Engine.

    Accepts a list of SemanticEnrichmentResult objects from M5.2D and
    produces a canonical, normalized, validated SemanticGraph.

    Usage:
        engine = RelationshipDiscoveryEngine()
        graph = engine.build_graph(enrichment_results)
        artifact = engine.export(graph)
    """

    def __init__(
        self,
        config: Optional[RelationshipDiscoveryEngineConfig] = None,
        resolver: Optional[RelationshipResolver] = None,
        classifier: Optional[RelationshipClassifier] = None,
        propagator: Optional[ConfidencePropagator] = None,
        builder: Optional[RelationshipBuilder] = None,
        validator: Optional[RelationshipValidator] = None,
        graph_builder: Optional[SemanticGraphBuilder] = None,
        normalizer: Optional[GraphNormalizer] = None,
        integrity_validator: Optional[GraphIntegrityValidator] = None,
        exporter: Optional[GraphExporter] = None,
    ) -> None:
        self._cfg = config or default_config
        self._resolver = resolver or RelationshipResolver(config=self._cfg)
        self._classifier = classifier or default_relationship_classifier
        self._propagator = propagator or default_confidence_propagator
        self._rel_builder = builder or RelationshipBuilder(confidence_propagator=self._propagator)
        self._validator = validator or RelationshipValidator(config=self._cfg)
        self._graph_builder = graph_builder or SemanticGraphBuilder(config=self._cfg)
        self._normalizer = normalizer or GraphNormalizer(config=self._cfg)
        self._integrity_validator = integrity_validator or GraphIntegrityValidator(config=self._cfg)
        self._exporter = exporter or default_graph_exporter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(
        self, enrichment_results: List[object]
    ) -> RelationshipDiscoveryResult:
        """
        Discover all relationships from *enrichment_results*.

        Returns a RelationshipDiscoveryResult.
        """
        diagnostics: List[str] = []
        relationships: List[SemanticRelationship] = []

        try:
            pairs = self._resolver.resolve_pairs(enrichment_results)
        except Exception as exc:
            return RelationshipDiscoveryResult(
                outcome=DiscoveryOutcome.ERROR,
                relationships=(),
                object_keys=tuple(
                    getattr(r, "object_key", "") for r in enrichment_results
                ),
                diagnostics=(f"RelationshipResolver failed: {exc}",),
            )

        for src, tgt in pairs:
            try:
                classification = self._classifier.classify(src, tgt)
                rel = self._rel_builder.build(src, tgt, classification)

                # Per-relationship validation
                vr = self._validator.validate_relationship(rel)
                if vr.has_errors:
                    diagnostics.append(
                        f"Relationship {rel.relationship_id!r} failed validation: "
                        + "; ".join(d.message for d in vr.diagnostics)
                    )
                    continue  # Skip invalid relationships

                relationships.append(rel)

            except Exception as exc:
                diagnostics.append(
                    f"Error building relationship for pair "
                    f"({getattr(getattr(src, 'anchor', None), 'anchor_id', '?')[:8]}, "
                    f"{getattr(getattr(tgt, 'anchor', None), 'anchor_id', '?')[:8]}): {exc}"
                )

        # Filter by confidence threshold
        before = len(relationships)
        relationships = [
            r for r in relationships
            if r.confidence.value >= self._cfg.min_relationship_confidence
        ]
        filtered = before - len(relationships)
        if filtered > 0:
            diagnostics.append(
                f"{filtered} relationships below confidence threshold "
                f"({self._cfg.min_relationship_confidence}) were excluded."
            )

        # Remove duplicate relationships (same relationship_id)
        seen_ids = set()
        deduped = []
        for r in relationships:
            if r.relationship_id not in seen_ids:
                seen_ids.add(r.relationship_id)
                deduped.append(r)
        relationships = deduped

        object_keys = tuple(
            getattr(r, "object_key", "") for r in enrichment_results
        )

        if not relationships and not pairs:
            outcome = DiscoveryOutcome.EMPTY
        elif not relationships:
            outcome = DiscoveryOutcome.PARTIAL
        elif diagnostics:
            outcome = DiscoveryOutcome.PARTIAL
        else:
            outcome = DiscoveryOutcome.COMPLETE

        return RelationshipDiscoveryResult(
            outcome=outcome,
            relationships=tuple(relationships),
            object_keys=object_keys,
            diagnostics=tuple(diagnostics),
        )

    def build_graph(
        self,
        enrichment_results: List[object],
        description: str = "",
    ) -> SemanticGraph:
        """
        Full pipeline: discover → build → normalize → validate.

        Returns a normalized, validated SemanticGraph.
        """
        try:
            discovery_result = self.discover(enrichment_results)
            graph = self._graph_builder.build(
                enrichment_results=enrichment_results,
                discovery_result=discovery_result,
                description=description,
            )
            graph = self._normalizer.normalize(graph)
            # Integrity validation — results appended to diagnostics as
            # informational (graph is still returned even if warnings exist)
            integrity_vr = self._integrity_validator.validate(graph)
            if integrity_vr.diagnostics:
                import dataclasses
                extra = tuple(
                    f"[{d.severity.value.upper()}] {d.code}: {d.message}"
                    for d in integrity_vr.diagnostics
                )
                graph = dataclasses.replace(
                    graph,
                    diagnostics=graph.diagnostics + extra,
                )
            return graph

        except RelationshipDiscoveryEngineError:
            raise
        except Exception as exc:
            raise RelationshipDiscoveryEngineError(
                f"Unexpected error in RelationshipDiscoveryEngine: {exc}"
            ) from exc

    def export(
        self,
        graph: SemanticGraph,
        format: GraphExportFormat = GraphExportFormat.DICT,
        indent: Optional[int] = None,
    ) -> GraphExportArtifact:
        """
        Export *graph* to a GraphExportArtifact for M5.3 consumption.
        """
        return self._exporter.export(graph, format=format, indent=indent)


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

#: Module-level singleton engine.
default_engine = RelationshipDiscoveryEngine()


def discover(enrichment_results: List[object]) -> RelationshipDiscoveryResult:
    """Convenience function: discover via the default engine."""
    return default_engine.discover(enrichment_results)
