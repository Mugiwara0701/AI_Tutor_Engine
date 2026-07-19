"""
modules/relationship_discovery_engine/relationship_resolver.py —
M5.2E Deliverable #1 (part): Candidate Pair Resolution.

Given a list of SemanticEnrichmentResults from M5.2D, the
RelationshipResolver produces all candidate (source, target) anchor
pairs eligible for relationship classification.

Filtering criteria:
- Both anchors must be present in their respective results.
- The anchor confidence must be >= config.min_node_confidence.
- Self-pairs (source == target anchor_id) are excluded unless
  config.allow_self_loops is True.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from modules.relationship_discovery_engine.config import (
    RelationshipDiscoveryEngineConfig,
    default_config,
)
from modules.relationship_discovery_engine.exceptions import RelationshipResolutionError

__all__ = [
    "AnchorPair",
    "RelationshipResolver",
    "default_relationship_resolver",
]

# Type alias: (source_enrichment_result, target_enrichment_result)
# We avoid importing SemanticEnrichmentResult here to keep the import
# graph clean; callers pass the objects as Any and we access them via
# getattr.
AnchorPair = Tuple[object, object]  # (source_result, target_result)


class RelationshipResolver:
    """
    Produces candidate (source, target) SemanticEnrichmentResult pairs
    from a list of SemanticEnrichmentResults.

    Does NOT import SemanticEnrichmentResult directly; accesses fields
    via attribute access so the coupling remains minimal.
    """

    def __init__(
        self,
        config: Optional[RelationshipDiscoveryEngineConfig] = None,
    ) -> None:
        self._cfg = config or default_config

    def resolve_pairs(self, enrichment_results: List[object]) -> List[AnchorPair]:
        """
        Return all valid (source, target) pairs from *enrichment_results*.

        A pair is valid when:
        1. Both results have a non-None anchor.
        2. Both anchor confidence values >= config.min_node_confidence.
        3. source.anchor.anchor_id != target.anchor.anchor_id unless
           allow_self_loops is True.

        The list is deterministically ordered:
        pairs are sorted by (source anchor_id, target anchor_id).
        """
        valid = self._filter_valid(enrichment_results)
        pairs: List[AnchorPair] = []

        for i, src in enumerate(valid):
            for j, tgt in enumerate(valid):
                if i == j:
                    continue
                src_id = src.anchor.anchor_id  # type: ignore[union-attr]
                tgt_id = tgt.anchor.anchor_id  # type: ignore[union-attr]
                if src_id == tgt_id and not self._cfg.allow_self_loops:
                    continue
                pairs.append((src, tgt))

        # Deterministic ordering
        pairs.sort(
            key=lambda p: (
                p[0].anchor.anchor_id,  # type: ignore[union-attr]
                p[1].anchor.anchor_id,  # type: ignore[union-attr]
            )
        )
        return pairs

    def _filter_valid(self, results: List[object]) -> List[object]:
        valid = []
        for r in results:
            anchor = getattr(r, "anchor", None)
            if anchor is None:
                continue
            confidence = getattr(getattr(anchor, "confidence", None), "value", 0.0)
            if confidence < self._cfg.min_node_confidence:
                continue
            valid.append(r)
        return valid


#: Module-level singleton.
default_relationship_resolver = RelationshipResolver()
