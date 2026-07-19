"""
modules/master_knowledge_compiler/graph_validator.py — M5.3
Deliverable #1: Graph Readiness Validation.

Validates a SemanticGraph (M5.2E) for compiler readiness before
compilation begins.  Reuses M5.1's ValidationResult contracts.
"""
from __future__ import annotations

from typing import List, Optional, Set

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.master_knowledge_compiler.config import MasterKnowledgeCompilerConfig, default_config
from modules.master_knowledge_compiler.exceptions import GraphReadinessError

__all__ = [
    "GraphReadinessValidator",
    "default_graph_readiness_validator",
]

# Minimum required versions for the source graph
_MIN_ENGINE_VERSION = (1, 0, 0)


def _parse_version(v: str):
    try:
        parts = v.split(".")
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return (0, 0, 0)


class GraphReadinessValidator:
    """
    Validates a SemanticGraph (M5.2E) for compilation readiness.

    Checks:
    1. Graph metadata present (graph_id, engine_version).
    2. Minimum engine version.
    3. Node uniqueness.
    4. Edge uniqueness.
    5. Non-empty node set.
    6. Node confidence >= config.min_node_confidence (where > 0).
    7. Graph build outcome is not ERROR.

    Reuses M5.1 ValidationResult / ValidationDiagnostic contracts.
    """

    def __init__(self, config: Optional[MasterKnowledgeCompilerConfig] = None) -> None:
        self._cfg = config or default_config

    def validate(self, graph: object) -> ValidationResult:
        """
        Validate *graph* (SemanticGraph from M5.2E).
        """
        diagnostics: List[ValidationDiagnostic] = []

        # 1. Metadata
        metadata = getattr(graph, "metadata", None)
        if metadata is None:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKC001",
                message="SemanticGraph.metadata is missing.",
                processor_name="GraphReadinessValidator",
            ))
        else:
            graph_id = getattr(metadata, "graph_id", "")
            if not graph_id:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="MKC002",
                    message="SemanticGraph.metadata.graph_id is empty.",
                    processor_name="GraphReadinessValidator",
                ))
            engine_version = getattr(metadata, "engine_version", "")
            if not engine_version:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="MKC003",
                    message="SemanticGraph.metadata.engine_version is empty.",
                    processor_name="GraphReadinessValidator",
                ))
            else:
                parsed = _parse_version(engine_version)
                if parsed < _MIN_ENGINE_VERSION:
                    diagnostics.append(ValidationDiagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        code="MKC004",
                        message=(
                            f"SemanticGraph.metadata.engine_version {engine_version!r} "
                            f"is below minimum supported {'.'.join(str(v) for v in _MIN_ENGINE_VERSION)}."
                        ),
                        processor_name="GraphReadinessValidator",
                    ))

        # 2. Graph outcome
        outcome = getattr(graph, "outcome", None)
        if outcome is not None and str(outcome).endswith("error"):
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.ERROR,
                code="MKC005",
                message=f"SemanticGraph.outcome is ERROR — not suitable for compilation.",
                processor_name="GraphReadinessValidator",
            ))

        nodes = getattr(graph, "nodes", ())
        edges = getattr(graph, "edges", ())

        # 3. Non-empty nodes
        if not nodes:
            diagnostics.append(ValidationDiagnostic(
                severity=DiagnosticSeverity.WARNING,
                code="MKC006",
                message="SemanticGraph has no nodes — compilation will produce an empty package.",
                processor_name="GraphReadinessValidator",
            ))

        # 4. Node uniqueness
        seen_node_ids: Set[str] = set()
        for node in nodes:
            nid = getattr(node, "node_id", "")
            if nid in seen_node_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="MKC007",
                    message=f"Duplicate node_id {nid!r} in SemanticGraph.",
                    processor_name="GraphReadinessValidator",
                ))
            else:
                seen_node_ids.add(nid)

        # 5. Edge uniqueness
        seen_edge_ids: Set[str] = set()
        for edge in edges:
            eid = getattr(edge, "edge_id", "")
            if eid in seen_edge_ids:
                diagnostics.append(ValidationDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code="MKC008",
                    message=f"Duplicate edge_id {eid!r} in SemanticGraph.",
                    processor_name="GraphReadinessValidator",
                ))
            else:
                seen_edge_ids.add(eid)

        # 6. Node confidence (only checked when threshold > 0)
        if self._cfg.min_node_confidence > 0.0:
            for node in nodes:
                conf = getattr(node, "confidence", 1.0)
                if conf < self._cfg.min_node_confidence:
                    diagnostics.append(ValidationDiagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        code="MKC009",
                        message=(
                            f"Node {getattr(node, 'node_id', '?')!r} confidence "
                            f"{conf} below min_node_confidence "
                            f"{self._cfg.min_node_confidence}."
                        ),
                        processor_name="GraphReadinessValidator",
                    ))

        # If strict mode, treat all warnings as errors
        if self._cfg.strict_graph_validation:
            diagnostics = [
                ValidationDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code=d.code,
                    message=d.message,
                    processor_name=d.processor_name,
                ) if d.severity == DiagnosticSeverity.WARNING else d
                for d in diagnostics
            ]

        return ValidationResult(diagnostics=tuple(diagnostics)) if diagnostics else SUCCESS


#: Module-level singleton.
default_graph_readiness_validator = GraphReadinessValidator()
