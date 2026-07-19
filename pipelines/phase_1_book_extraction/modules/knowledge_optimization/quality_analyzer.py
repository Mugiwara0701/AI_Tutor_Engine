"""
modules/knowledge_optimization/quality_analyzer.py — M5.4
Deliverable #8: Knowledge Quality Analysis.

Detects structural quality issues in the compiled knowledge package
and generates a structured KnowledgeQualityReport.  No LLM, no narrative.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from modules.knowledge_optimization.config import KnowledgeOptimizationConfig, default_config
from modules.knowledge_optimization.enums import (
    OptimizationOutcome, QualityIssueType, QualityIssueSeverity,
)
from modules.knowledge_optimization.models import KnowledgeQualityReport, QualityIssue

__all__ = ["KnowledgeQualityAnalyzer", "default_quality_analyzer"]


class KnowledgeQualityAnalyzer:
    """
    Detects quality issues in a MasterKnowledgePackage (M5.3).
    Returns a KnowledgeQualityReport.  Never modifies input.
    """

    def __init__(self, config: Optional[KnowledgeOptimizationConfig] = None) -> None:
        self._cfg = config or default_config

    def analyze(self, package: object) -> KnowledgeQualityReport:
        issues: List[QualityIssue] = []
        ci  = getattr(package, "concept_index", None)
        dep = getattr(package, "dependency_map", None)
        xr  = getattr(package, "cross_reference_index", None)

        entries   = getattr(ci, "entries", ()) if ci else ()
        dep_edges = getattr(dep, "edges", ()) if dep else ()
        xr_entries = getattr(xr, "entries", ()) if xr else ()

        # Build adjacency for connectivity checks
        connected: Set[str] = set()
        for edge in dep_edges:
            connected.add(getattr(edge, "source_node_id", ""))
            connected.add(getattr(edge, "target_node_id", ""))

        xr_map: Dict[str, object] = {
            getattr(e, "node_id", ""): e for e in xr_entries
        }

        for entry in entries:
            nid  = getattr(entry, "node_id", "")
            conf = float(getattr(entry, "confidence", 1.0))
            cat  = getattr(entry, "category", None)
            cat_v = cat.value if hasattr(cat, "value") else str(cat or "other")

            # 1. Isolated concepts
            if nid not in connected:
                issues.append(QualityIssue(
                    issue_type=QualityIssueType.ISOLATED_CONCEPT,
                    severity=QualityIssueSeverity.LOW,
                    node_id=nid,
                    message=f"Concept {nid!r} has no dependency edges.",
                    suggestion="Consider adding prerequisite or related-concept links.",
                ))

            # 2. Low confidence
            if conf < self._cfg.min_confidence_threshold:
                issues.append(QualityIssue(
                    issue_type=QualityIssueType.LOW_CONFIDENCE,
                    severity=QualityIssueSeverity.MEDIUM,
                    node_id=nid,
                    message=f"Concept {nid!r} confidence {conf:.3f} below threshold {self._cfg.min_confidence_threshold}.",
                    suggestion="Review source structural/semantic analysis quality.",
                ))

            # 3. Missing examples (for concept/definition/principle)
            if cat_v in ("concept", "definition", "principle"):
                xre = xr_map.get(nid)
                if xre is not None and not getattr(xre, "examples", ()):
                    issues.append(QualityIssue(
                        issue_type=QualityIssueType.MISSING_EXAMPLES,
                        severity=QualityIssueSeverity.LOW,
                        node_id=nid,
                        message=f"Concept {nid!r} ({cat_v}) has no example cross-references.",
                        suggestion="Link at least one worked example to this concept.",
                    ))

            # 4. Sparse assessments
            if cat_v in ("concept", "principle", "law", "theorem"):
                xre = xr_map.get(nid)
                if xre is not None and not getattr(xre, "assessments", ()):
                    issues.append(QualityIssue(
                        issue_type=QualityIssueType.SPARSE_ASSESSMENTS,
                        severity=QualityIssueSeverity.INFO,
                        node_id=nid,
                        message=f"Concept {nid!r} ({cat_v}) has no assessment cross-references.",
                        suggestion="Add assessment or MCQ links for self-check purposes.",
                    ))

            # 5. Weak cross-linking
            xre = xr_map.get(nid)
            if xre is not None:
                total_refs = sum(
                    len(getattr(xre, f, ()))
                    for f in ("examples", "figures", "experiments",
                              "procedures", "assessments", "tables", "related")
                )
                if total_refs < self._cfg.min_cross_links_per_concept:
                    issues.append(QualityIssue(
                        issue_type=QualityIssueType.WEAK_CROSS_LINKING,
                        severity=QualityIssueSeverity.LOW,
                        node_id=nid,
                        message=f"Concept {nid!r} has only {total_refs} cross-references (threshold: {self._cfg.min_cross_links_per_concept}).",
                        suggestion="Increase semantic relationships to related educational objects.",
                    ))

        # 6. Circular dependencies
        if self._cfg.enable_cycle_detection:
            cycles = self._detect_cycles(
                [getattr(e, "node_id", "") for e in entries],
                dep_edges,
            )
            for cycle_node in cycles:
                issues.append(QualityIssue(
                    issue_type=QualityIssueType.CIRCULAR_DEPENDENCY,
                    severity=QualityIssueSeverity.HIGH,
                    node_id=cycle_node,
                    message=f"Node {cycle_node!r} participates in a dependency cycle.",
                    suggestion="Review and break the circular dependency.",
                ))

        # Sort: CRITICAL first, then HIGH, MEDIUM, LOW, INFO, then node_id
        severity_order = {
            QualityIssueSeverity.CRITICAL: 0, QualityIssueSeverity.HIGH: 1,
            QualityIssueSeverity.MEDIUM: 2, QualityIssueSeverity.LOW: 3,
            QualityIssueSeverity.INFO: 4,
        }
        issues.sort(key=lambda i: (severity_order.get(i.severity, 5), i.node_id))

        counts = defaultdict(int)
        for iss in issues:
            counts[iss.severity.value] += 1

        concepts_with_issues = tuple(sorted({i.node_id for i in issues}))
        total = len(entries)
        score = round(max(0.0, 1.0 - len(concepts_with_issues) / max(total, 1)), 4) if total else 1.0

        outcome = OptimizationOutcome.COMPLETE if entries else OptimizationOutcome.EMPTY

        return KnowledgeQualityReport(
            issues=tuple(issues),
            total_issues=len(issues),
            critical_count=counts["critical"],
            high_count=counts["high"],
            medium_count=counts["medium"],
            low_count=counts["low"],
            info_count=counts["info"],
            overall_quality_score=score,
            concepts_with_issues=concepts_with_issues,
            outcome=outcome,
        )

    @staticmethod
    def _detect_cycles(node_ids: List[str], edges: object) -> Set[str]:
        """Return node_ids that participate in dependency cycles."""
        adjacency: Dict[str, List[str]] = defaultdict(list)
        for edge in (edges or ()):
            src = getattr(edge, "source_node_id", "")
            tgt = getattr(edge, "target_node_id", "")
            if src and tgt:
                adjacency[src].append(tgt)

        visited: Set[str] = set()
        in_stack: Set[str] = set()
        cycle_nodes: Set[str] = set()

        def dfs(node: str) -> None:
            visited.add(node)
            in_stack.add(node)
            for nbr in sorted(adjacency.get(node, [])):
                if nbr not in visited:
                    dfs(nbr)
                elif nbr in in_stack:
                    cycle_nodes.add(nbr)
                    cycle_nodes.add(node)
            in_stack.discard(node)

        for nid in sorted(node_ids):
            if nid not in visited:
                dfs(nid)

        return cycle_nodes


default_quality_analyzer = KnowledgeQualityAnalyzer()
