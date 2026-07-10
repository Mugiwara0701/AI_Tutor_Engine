"""
knowledge_graph/schema.py — Phase C0 Task 1: Knowledge Graph Core Schema.

SCOPE: this module defines the SHAPE of every top-level Knowledge Graph
artifact -- plain, deterministic dataclasses, mirroring every Compiler
IR artifact's own "plain, storable dict" convention
(compiler/validation.py's ValidationReport.to_dict(), compiler/build.py's
CompilerManifest/CompilerStatistics, compiler/finalize.py's
CompilerBuildSummary). It does NOT construct a single instance of any of
these against real data anywhere in this codebase -- every dataclass
below is a schema only, populated for the first time by a future C-phase
(see docs/knowledge_graph_architecture.md's Pipeline section for exactly
which phase populates which artifact).

WHY EACH ARTIFACT EXISTS (mirrors Compiler IR's own artifact split, one
for one):

    Compiler IR artifact                    Knowledge Graph artifact
    -------------------------------------   -------------------------------------
    RegistryManager (populated registries)  KnowledgeGraph (populated node/edge
                                             registries)
    CompilerManifest                        KnowledgeGraphManifest
    CompilerStatistics                      KnowledgeGraphStatistics
    ValidationReport                        KnowledgeGraphValidationReport
    CompilerReadinessReport                 KnowledgeGraphReadinessReport
    CompilerBuildSummary                    KnowledgeGraphBuildSummary
    (compiler/state.py's module slots)      KnowledgeGraphState (see state.py)

`KnowledgeGraphMetadata` has no direct Compiler IR counterpart -- it is
new, small, embedded record (graph namespace, source chapter identifier,
source compiler fingerprint) carried on `KnowledgeGraph` itself so a
graph, once built, is self-describing about which exact Compiler IR
build it was derived from (see FIELD NOTES on `KnowledgeGraph` below).

DETERMINISM: every field on every dataclass below is either a plain
scalar, a plain container of scalars, or another dataclass from this
same module -- no field is typed to hold a live object reference,
callable, or anything else that would make two independently-built
instances compare unequal despite describing the same graph. This
mirrors every Compiler IR artifact's own determinism property.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------
# This schema's own version marker -- independent of
# identity.IDENTITY_VERSION, independent of every compiler-side
# *_VERSION constant, and independent of config.SCHEMA_VERSION. Bump
# only if a dataclass SHAPE in this module changes.
# --------------------------------------------------------------------------
KNOWLEDGE_GRAPH_SCHEMA_VERSION = "C0.1"


# --------------------------------------------------------------------------
# KnowledgeGraphMetadata
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphMetadata:
    """Self-describing record of which exact Compiler IR build a graph
    was (or, in Phase C0, will eventually be) derived from -- the one
    piece of information every other artifact below needs but none of
    them owns individually. Deliberately small: it names the source
    Compiler IR (`compiler_manifest`'s own identity fields, not a copy
    of the whole manifest) rather than embedding compiler/build.py's
    CompilerManifest wholesale, so this dataclass stays independent of
    that module's own field set changing shape later.

    graph_id / graph_urn: this graph's own identity (see
    knowledge_graph/identity.py::graph_id()/graph_urn()) -- NOT the
    source chapter's compiler identity.
    source_chapter_identifier: the same `chapter_identifier` Compiler
    IR's own CompilerManifest carries (compiler/build.py), so a graph
    can always be traced back to the chapter it was built from.
    source_compiler_version / source_compiler_fingerprint: copied,
    read-only, from the Compiler IR build this graph was derived from
    (compiler/build.py's COMPILER_VERSION and
    compiler/fingerprints.py's own compiler_fingerprint) -- lets a
    consumer detect a graph that is now stale relative to its source
    Compiler IR without re-deriving anything.
    """

    graph_id: str
    graph_urn: str
    graph_version: str = KNOWLEDGE_GRAPH_SCHEMA_VERSION
    identity_version: str = "C0.1"  # mirrors identity.IDENTITY_VERSION
    source_chapter_identifier: Optional[str] = None
    source_compiler_version: Optional[str] = None
    source_compiler_fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# KnowledgeGraph -- the top-level, populated artifact (schema only here;
# never instantiated with real node/edge registries in Phase C0).
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraph:
    """The Knowledge Graph itself: one `KnowledgeGraphMetadata` plus the
    populated node/edge registries a future C1-C3 pipeline will build
    (see knowledge_graph/registries.py -- `GraphRegistryManager` is the
    exact analogue of compiler/registry_manager.py's own
    `RegistryManager`, reused, not reinvented).

    `nodes`/`edges` are typed `Any` here on purpose: this schema module
    does not import knowledge_graph.registries (avoiding a schema<->
    registries import cycle, the same layering compiler/validation.py
    already keeps relative to compiler/registry.py -- validation reads
    a RegistryManager without registry.py needing to know
    ValidationReport exists). A future C1 constructor is expected to
    populate these with a `GraphRegistryManager` instance.

    This dataclass is NEVER instantiated with real registries anywhere
    in Phase C0 -- see this module's own docstring."""

    metadata: KnowledgeGraphMetadata
    nodes: Any = None  # future: GraphRegistryManager-owned node registries
    edges: Any = None  # future: GraphRegistryManager-owned edge registries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "nodes": self.nodes,
            "edges": self.edges,
        }


# --------------------------------------------------------------------------
# KnowledgeGraphManifest -- mirrors compiler/build.py's CompilerManifest
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphManifest:
    """Identity/versioning record for one Knowledge Graph build --
    the Knowledge Graph analogue of compiler/build.py's
    `CompilerManifest`. Field set deliberately parallels
    CompilerManifest's own field set, one for one, so a consumer already
    familiar with the Compiler IR manifest shape recognizes this one
    immediately.

    `graph_status` mirrors CompilerManifest's OWN documented
    `manifest_generation_status` naming choice (see
    docs/phase_b_completion_report.md §5a and compiler/build.py's
    module docstring's DISAMBIGUATION section) -- i.e. this field
    means only "did manifest generation for this graph complete",
    never a readiness/correctness verdict about the graph as a whole.
    A future KnowledgeGraphBuildSummary.build_status (mirroring
    compiler/finalize.py's own CompilerBuildSummary.build_status) is
    where that broader verdict belongs -- learning directly from the
    B5.1/B5.3 audit finding rather than reintroducing the same
    ambiguity at the start of Phase C.
    """

    generated_at: str = ""
    graph_schema_version: str = KNOWLEDGE_GRAPH_SCHEMA_VERSION
    identity_version: str = "C0.1"
    graph_id: str = ""
    graph_urn: str = ""
    source_chapter_identifier: Optional[str] = None
    node_registry_versions: Dict[str, str] = field(default_factory=dict)
    node_count: int = 0
    edge_count: int = 0
    node_type_counts: Dict[str, int] = field(default_factory=dict)
    edge_type_counts: Dict[str, int] = field(default_factory=dict)
    graph_status: str = "unbuilt"
    graph_generation_status: str = "unbuilt"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# KnowledgeGraphStatistics -- mirrors compiler/build.py's
# CompilerStatistics
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphStatistics:
    """Descriptive breakdown of one Knowledge Graph build -- the
    Knowledge Graph analogue of compiler/build.py's
    `CompilerStatistics`."""

    generated_at: str = ""
    node_registry_sizes: Dict[str, int] = field(default_factory=dict)
    edges_by_type: Dict[str, int] = field(default_factory=dict)
    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_source_registry: Dict[str, int] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# KnowledgeGraphValidationReport -- mirrors compiler/validation.py's
# ValidationReport
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphValidationReport:
    """Integrity verdict for one Knowledge Graph build -- the Knowledge
    Graph analogue of compiler/validation.py's `ValidationReport`. Field
    set intentionally mirrors that dataclass's own
    status/errors/warnings/summaries shape.

    PHASE C3 ADDITION (Knowledge Graph Validation & Integrity): every
    field above this note is exactly as Phase C0 defined it -- untouched,
    same name, same meaning, same default. `validation_version`,
    `generated_at`, `passed_checks`, `failed_checks`, `registry_summary`,
    and `statistics` are new, additive fields Phase C3's own Task 6
    report spec requires that Phase C0's speculative schema (written
    before any concrete validation rule existed) simply didn't anticipate
    -- the same "frozen phase, additive-only extension" pattern
    compiler/build.py's own COMPILER_VERSION bump and compiler/state.py's
    own repeated PHASE B5.1/B5.2/B5.3 ADDITION sections already establish
    for this project. Safe to extend without a call-site migration:
    nothing in this codebase constructs a KnowledgeGraphValidationReport
    with real data before Phase C3 (grep-confirmed -- every prior
    reference is a type hint or a docstring mention), so there is no
    existing caller whose behavior this could change.

    `to_dict()` below emits BOTH the original seven keys (unchanged) AND
    the new ones -- including `overall_status` as an explicit alias of
    the pre-existing `status` field (same value, Task 6's own literal
    field name) and `validation_statistics` as the emitted key name for
    the `statistics` field (Task 6's own literal name for that data) --
    so a reader expecting either naming convention finds what it's
    looking for, and nothing that could have depended on the original
    shape loses any key.
    """

    status: str = "unknown"  # "pass" | "fail" | "unknown"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    node_summary: Dict[str, Any] = field(default_factory=dict)
    edge_summary: Dict[str, Any] = field(default_factory=dict)
    integrity_summary: Dict[str, Any] = field(default_factory=dict)
    determinism_summary: Dict[str, Any] = field(default_factory=dict)
    # -- Phase C3 additions (see docstring above) --
    validation_version: str = ""
    generated_at: str = ""
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    registry_summary: Dict[str, Any] = field(default_factory=dict)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            # -- original Phase C0 keys, unchanged --
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "node_summary": self.node_summary,
            "edge_summary": self.edge_summary,
            "integrity_summary": self.integrity_summary,
            "determinism_summary": self.determinism_summary,
            # -- Phase C3 additions --
            "validation_version": self.validation_version,
            "generated_at": self.generated_at,
            "overall_status": self.status,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "registry_summary": self.registry_summary,
            "validation_statistics": self.statistics,
        }


# --------------------------------------------------------------------------
# KnowledgeGraphReadinessReport -- mirrors
# compiler/fingerprints.py's CompilerReadinessReport
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphReadinessReport:
    """Read-only readiness verdict for one Knowledge Graph build -- the
    Knowledge Graph analogue of compiler/fingerprints.py's
    `CompilerReadinessReport`."""

    ready: bool = False
    checks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    readiness_summary: Dict[str, int] = field(
        default_factory=lambda: {
            "total_checks": 0,
            "passed_count": 0,
            "failed_count": 0,
            "warning_count": 0,
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# KnowledgeGraphBuildSummary -- mirrors compiler/finalize.py's
# CompilerBuildSummary
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphBuildSummary:
    """One deterministic aggregation of every artifact above -- the
    Knowledge Graph analogue of compiler/finalize.py's
    `CompilerBuildSummary`. `build_status` here mirrors
    CompilerBuildSummary.build_status's OWN meaning exactly (the final
    READY/READY_WITH_WARNINGS/FAILED-shaped verdict for the whole
    graph build) -- never the narrower "generation completed" meaning
    `KnowledgeGraphManifest.graph_status` carries above. See that
    dataclass's own docstring for why this distinction is deliberate
    (learned directly from the Phase B audit's build_status finding)."""

    generated_at: str = ""
    graph_schema_version: str = KNOWLEDGE_GRAPH_SCHEMA_VERSION
    identity_version: str = "C0.1"
    graph_status: str = "unbuilt"
    build_status: str = "NOT_BUILT"
    total_node_registries: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    readiness_summary: Dict[str, Any] = field(default_factory=dict)
    graph_fingerprint: Optional[str] = None
    overall_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# KnowledgeGraphState -- the SCHEMA of the "current knowledge graph
# compilation state" module-level slots knowledge_graph/state.py owns
# (see that module for the actual get/set/has lifecycle functions,
# mirroring compiler/state.py's own pattern). This dataclass exists so
# the full set of state slots is documented and introspectable in one
# place, the same way this module documents every other artifact's
# shape -- knowledge_graph/state.py itself does not store a
# KnowledgeGraphState instance; it stores each field as its own
# module-level slot, exactly like compiler/state.py stores
# `_CURRENT_REGISTRY_MANAGER` etc. as separate slots rather than one
# combined "CompilerState" object.
# --------------------------------------------------------------------------

@dataclass
class KnowledgeGraphState:
    """Documents the shape of knowledge_graph/state.py's module-level
    "current graph compilation state" -- see that module. All fields
    default to the empty/unset value a freshly-reset state would have."""

    graph: Optional[KnowledgeGraph] = None
    manifest: Optional[KnowledgeGraphManifest] = None
    statistics: Optional[KnowledgeGraphStatistics] = None
    validation_report: Optional[KnowledgeGraphValidationReport] = None
    # -- Phase C4.2 additions (knowledge_graph/fingerprints.py) --
    registry_fingerprints: Optional[Dict[str, str]] = None
    graph_fingerprint: Optional[str] = None
    readiness_report: Optional[KnowledgeGraphReadinessReport] = None
    build_summary: Optional[KnowledgeGraphBuildSummary] = None
    final_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph": self.graph.to_dict() if self.graph else None,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "statistics": self.statistics.to_dict() if self.statistics else None,
            "validation_report": (
                self.validation_report.to_dict() if self.validation_report else None
            ),
            "registry_fingerprints": self.registry_fingerprints,
            "graph_fingerprint": self.graph_fingerprint,
            "readiness_report": (
                self.readiness_report.to_dict() if self.readiness_report else None
            ),
            "build_summary": (
                self.build_summary.to_dict() if self.build_summary else None
            ),
            "final_status": self.final_status,
        }