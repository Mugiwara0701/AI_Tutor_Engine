"""
knowledge_graph/pipeline_architecture.py — Phase C0 Task 7: Graph
Pipeline Architecture.

SCOPE: this module documents the FUTURE Phase C pipeline's execution
order as plain, inert data (a tuple of `PipelineStageSpec` records) --
it contains no pipeline code, no pass function, and calls nothing. It is
the Knowledge Graph analogue of docs/phase_b_completion_report.md's own
"Compiler pipeline" ASCII diagram (§3 of that document), expressed as an
importable/introspectable constant instead of prose, so a future C-phase
implementer (and this module's own architecture tests) has one
unambiguous, machine-checkable source for "what runs after what" rather
than two documents (this one and
docs/knowledge_graph_architecture.md) that could drift apart. That docs
file's own Pipeline section is expected to render this same data as
prose/diagram, not redefine it.

PHASE C0 ITSELF IS NOT A PIPELINE STAGE: C0 (this whole package, as of
this file) is architecture -- it runs before C1, is not re-run per
chapter, and produces no per-chapter artifact of its own. It is
deliberately left out of PIPELINE_STAGES below, the same way Phase A
(schema foundation) is not listed as a row in
docs/phase_b_completion_report.md's own §3 Compiler pipeline diagram --
both are prerequisites the pipeline stands on, not steps the pipeline
executes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class PipelineStageSpec:
    """One future Phase C pipeline stage, as an inert spec -- no
    `run()` method, no import of any stage's own (not-yet-existing)
    implementation module. Mirrors this project's own existing
    "document the order in prose/table, implement it inside pipeline.py
    later" precedent (see docs/phase_b_completion_report.md §3/§4's
    own two tables, which document compiler/*.py passes that already
    exist -- here, every `module` value below names a module that does
    NOT yet exist, since that's exactly what "no implementation" for
    Phase C0 means)."""

    phase: str
    name: str
    module: str
    reads: Tuple[str, ...]
    produces: Tuple[str, ...]


# --------------------------------------------------------------------------
# The full future Phase C pipeline, in fixed execution order (Task 7's
# own example order, adopted as-is). Nothing in this codebase iterates
# or executes this tuple in Phase C0 -- it exists purely as documented,
# introspectable data for this module's own architecture tests and for
# docs/knowledge_graph_architecture.md to render.
# --------------------------------------------------------------------------
PIPELINE_STAGES: Tuple[PipelineStageSpec, ...] = (
    PipelineStageSpec(
        phase="C1",
        name="Node Construction",
        module="knowledge_graph.build_nodes",
        reads=("compiler.RegistryManager (Compiler IR)",),
        produces=("GraphNodeBase instances, inserted into the node registry",),
    ),
    PipelineStageSpec(
        phase="C2",
        name="Edge Construction",
        module="knowledge_graph.build_edges",
        reads=(
            "node registry (C1 output)",
            "compiler.relationships.RelationshipRegistry (Compiler IR)",
        ),
        produces=("GraphEdgeBase instances, inserted into the edge registry",),
    ),
    PipelineStageSpec(
        phase="C3",
        name="Cross-Link Resolution",
        module="knowledge_graph.resolve_cross_links",
        reads=("node registry", "edge registry"),
        produces=("cross-registry link integrity (e.g. dangling endpoint repair/report)",),
    ),
    PipelineStageSpec(
        phase="C4",
        name="Educational Semantics",
        module="knowledge_graph.educational_semantics",
        reads=("node registry", "edge registry"),
        produces=("derived educational-role annotations on nodes/edges",),
    ),
    PipelineStageSpec(
        phase="C5",
        name="Validation",
        module="knowledge_graph.graph_validation",
        reads=("KnowledgeGraph (C1-C4 output)",),
        produces=("KnowledgeGraphValidationReport",),
    ),
    PipelineStageSpec(
        phase="C6",
        name="Optimization",
        module="knowledge_graph.optimize",
        reads=("KnowledgeGraph", "KnowledgeGraphValidationReport"),
        produces=("an optimized KnowledgeGraph (e.g. redundant-edge pruning)",),
    ),
    PipelineStageSpec(
        phase="C7",
        name="Metadata",
        module="knowledge_graph.graph_metadata",
        reads=("KnowledgeGraph",),
        produces=("KnowledgeGraphManifest", "KnowledgeGraphStatistics"),
    ),
    PipelineStageSpec(
        phase="C8",
        name="Finalization",
        module="knowledge_graph.finalize",
        reads=(
            "KnowledgeGraphValidationReport",
            "KnowledgeGraphManifest",
            "KnowledgeGraphStatistics",
        ),
        produces=("KnowledgeGraphReadinessReport", "KnowledgeGraphBuildSummary"),
    ),
    PipelineStageSpec(
        phase="C9",
        name="Freeze",
        module="knowledge_graph.freeze",
        reads=("KnowledgeGraphBuildSummary",),
        produces=("a frozen, immutable KnowledgeGraph for this chapter",),
    ),
)


def stage_names_in_order() -> Tuple[str, ...]:
    """Convenience accessor for architecture tests -- returns just the
    ordered `phase` values (e.g. ("C1", "C2", ..., "C9"))."""
    return tuple(stage.phase for stage in PIPELINE_STAGES)