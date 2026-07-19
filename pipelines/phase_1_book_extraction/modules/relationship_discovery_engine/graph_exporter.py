"""
modules/relationship_discovery_engine/graph_exporter.py — M5.2E
Deliverable #7: Graph Export.

Produces the final, canonical, serializable SemanticGraph artifact
ready for M5.3 consumption.

The graph is:
- immutable (frozen dataclass)
- serializable (to_dict() / to_json())
- versioned
- deterministic (same input always produces same output)

GraphExporter does NOT modify the graph; it only serializes it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from modules.relationship_discovery_engine.enums import GraphExportFormat
from modules.relationship_discovery_engine.exceptions import GraphExportError
from modules.relationship_discovery_engine.models import SemanticGraph

__all__ = [
    "GraphExporter",
    "GraphExportArtifact",
    "default_graph_exporter",
]


class GraphExportArtifact:
    """
    The result of a GraphExporter.export() call.

    Attributes:
        graph:        The original SemanticGraph (frozen, unchanged).
        format:       The export format used.
        payload:      The serialized payload (dict or JSON string).
        node_count:   Number of nodes exported.
        edge_count:   Number of edges exported.
        engine_version: Engine version from graph metadata.
        graph_id:     Graph ID from graph metadata.
    """

    __slots__ = (
        "graph", "format", "payload",
        "node_count", "edge_count",
        "engine_version", "graph_id",
    )

    def __init__(
        self,
        graph: SemanticGraph,
        format: GraphExportFormat,
        payload: Any,
    ) -> None:
        self.graph = graph
        self.format = format
        self.payload = payload
        self.node_count = len(graph.nodes)
        self.edge_count = len(graph.edges)
        self.engine_version = graph.metadata.engine_version
        self.graph_id = graph.metadata.graph_id

    def to_dict(self) -> Dict[str, Any]:
        """Return an export summary (not the full payload)."""
        return {
            "graph_id": self.graph_id,
            "engine_version": self.engine_version,
            "format": self.format.value,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "outcome": self.graph.outcome.value,
        }


class GraphExporter:
    """
    Exports a SemanticGraph to a serializable artifact for M5.3.

    Does NOT modify the graph.
    """

    def export(
        self,
        graph: SemanticGraph,
        format: GraphExportFormat = GraphExportFormat.DICT,
        indent: Optional[int] = None,
    ) -> GraphExportArtifact:
        """
        Export *graph* to the given *format*.

        Parameters
        ----------
        graph:
            The SemanticGraph to export.
        format:
            DICT (default) or JSON.
        indent:
            JSON indent level (only used when format=JSON).
        """
        try:
            graph_dict = graph.to_dict()
        except Exception as exc:
            raise GraphExportError(
                f"Failed to serialize SemanticGraph {graph.metadata.graph_id!r}: {exc}"
            ) from exc

        if format == GraphExportFormat.JSON:
            try:
                payload = json.dumps(graph_dict, ensure_ascii=False, indent=indent, sort_keys=True)
            except Exception as exc:
                raise GraphExportError(
                    f"Failed to JSON-encode SemanticGraph "
                    f"{graph.metadata.graph_id!r}: {exc}"
                ) from exc
        else:
            payload = graph_dict

        return GraphExportArtifact(
            graph=graph,
            format=format,
            payload=payload,
        )

    def export_as_json(
        self,
        graph: SemanticGraph,
        indent: int = 2,
    ) -> str:
        """Convenience wrapper: export to JSON string."""
        artifact = self.export(graph, format=GraphExportFormat.JSON, indent=indent)
        return artifact.payload  # type: ignore[return-value]

    def export_as_dict(self, graph: SemanticGraph) -> Dict[str, Any]:
        """Convenience wrapper: export to plain dict."""
        artifact = self.export(graph, format=GraphExportFormat.DICT)
        return artifact.payload  # type: ignore[return-value]


#: Module-level singleton.
default_graph_exporter = GraphExporter()
