"""
build_metadata/build.py — Phase E1: BuildMetadata (the top-level
aggregation artifact) and its two per-compiler-stage sub-blocks,
CompilerMetadata and GraphMetadata.

SCOPE (read this before touching anything else): Phase A, Phase B,
Phase C, and Phase D (D1 System Integrity, D2 Determinism, D3 Release
Readiness) are all frozen -- this module does not redesign compiler/,
knowledge_graph/, or validation/. It ONLY adds one more read-only pass,
mirroring compiler/finalize.py's, knowledge_graph/finalize.py's, and
validation/release.py's own "aggregate what earlier phases already
computed into one artifact" role, one layer up: it aggregates the
Compiler's, Knowledge Graph's, and Release's own already-computed
artifacts (CompilerMetadata / GraphMetadata below) together with this
phase's own two new deterministic/operational blocks
(CompilationMetadata, ConfigurationMetadata -- see those modules) and one
version-aggregation block (VersionMetadata) into a single BuildMetadata
record. It never regenerates, repairs, recomputes, or mutates a single
field anywhere in the Compiler IR, the Knowledge Graph, or any earlier
report, and it never inserts into, updates, or removes from any
registry.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Dependency Graph (E2), not Change Detection (E3), not Incremental
Compilation (E4), not Metadata Validation, not a Build Cache. It performs
no new validation, determinism, or readiness checking of its own --
every verdict BuildMetadata carries (final_compiler_status,
final_graph_status, release_status) is read, never recomputed.

REUSE, DON'T RECOMPUTE: every field CompilerMetadata/GraphMetadata below
carries is read from artifacts Phases B5.1-B5.3/C4.1-C4.3 already
produced this chapter (the Compiler/Knowledge Graph Manifest, Statistics,
Registry Fingerprints, [Compiler/Graph] Fingerprint, Readiness Report,
Build Summary, and Final Status) -- nothing here re-scans a registry,
re-derives a fingerprint, or re-validates anything a second time.

BuildMetadata itself remains completely read-only: it is never attached
to `chapter_dict` and never reaches json_writer.assemble_chapter_json's
output -- the same "internal diagnostic, never serialized into Chapter
JSON" treatment every earlier Phase B5/C4/D artifact already gets.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .compilation_metadata import generate_compilation_metadata
from .configuration_metadata import generate_configuration_metadata
from .version_metadata import generate_version_metadata

# This module's own version marker -- independent of every other *_VERSION
# constant in this codebase (see e.g. compiler/finalize.py's own
# FINALIZE_VERSION). Bump only if the SHAPE this module produces itself
# changes in a way a consumer of `build_metadata` should be able to
# detect.
BUILD_METADATA_VERSION = "E1.1"


# --------------------------------------------------------------------------
# CompilerMetadata -- read-only aggregation of Phase B's own artifacts
# --------------------------------------------------------------------------

@dataclass
class CompilerMetadata:
    """Aggregates every Compiler-side artifact Phase B already produced
    this chapter. Purely a data holder; all aggregation happens in
    generate_compiler_metadata() below. Every field is a direct read of
    an already-computed argument -- nothing here re-derives any of
    them."""

    compiler_manifest: Optional[Dict[str, Any]]
    compiler_statistics: Optional[Dict[str, Any]]
    registry_fingerprints: Optional[Dict[str, str]]
    compiler_fingerprint: Optional[str]
    compiler_readiness_report: Optional[Dict[str, Any]]
    compiler_build_summary: Optional[Dict[str, Any]]
    final_compiler_status: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compiler_metadata(
    *,
    compiler_manifest: Optional[Dict[str, Any]],
    compiler_statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    compiler_readiness_report: Optional[Dict[str, Any]],
    compiler_build_summary: Optional[Dict[str, Any]],
    final_compiler_status: Optional[str],
) -> Dict[str, Any]:
    """Phase E1: read-only aggregation of every Compiler-side artifact
    Phase B5.1-B5.3 already produced this chapter. Every argument is
    already in scope in pipeline.py's process_chapter() by the time
    Phase E1's own integration point runs (see pipeline.py's own comment
    at the Phase E1 call site) -- this function performs no computation
    beyond wrapping them into one CompilerMetadata dict."""
    metadata = CompilerMetadata(
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        registry_fingerprints=registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_build_summary,
        final_compiler_status=final_compiler_status,
    )
    return metadata.to_dict()


# --------------------------------------------------------------------------
# GraphMetadata -- read-only aggregation of Phase C's own artifacts
# --------------------------------------------------------------------------

@dataclass
class GraphMetadata:
    """Aggregates every Knowledge-Graph-side artifact Phase C already
    produced this chapter. Purely a data holder; all aggregation happens
    in generate_graph_metadata() below. Exact same shape as
    CompilerMetadata above, one artifact over."""

    knowledge_graph_manifest: Optional[Dict[str, Any]]
    knowledge_graph_statistics: Optional[Dict[str, Any]]
    registry_fingerprints: Optional[Dict[str, str]]
    graph_fingerprint: Optional[str]
    knowledge_graph_readiness_report: Optional[Dict[str, Any]]
    knowledge_graph_build_summary: Optional[Dict[str, Any]]
    final_graph_status: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_graph_metadata(
    *,
    knowledge_graph_manifest: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    graph_fingerprint: Optional[str],
    knowledge_graph_readiness_report: Optional[Dict[str, Any]],
    knowledge_graph_build_summary: Optional[Dict[str, Any]],
    final_graph_status: Optional[str],
) -> Dict[str, Any]:
    """Phase E1: read-only aggregation of every Knowledge-Graph-side
    artifact Phase C4.1-C4.3 already produced this chapter. Same
    "already in scope, no new computation" rule as
    generate_compiler_metadata() above."""
    metadata = GraphMetadata(
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        registry_fingerprints=registry_fingerprints,
        graph_fingerprint=graph_fingerprint,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_build_summary,
        final_graph_status=final_graph_status,
    )
    return metadata.to_dict()


# --------------------------------------------------------------------------
# DSTMetadata -- Milestone 5.2: read-only aggregation of the Document
# Structure Tree's own already-computed artifact
# --------------------------------------------------------------------------

@dataclass
class DSTMetadata:
    """Aggregates the Document Structure Tree artifact Milestone 5.1
    already produced this chapter (document_structure_tree/, DST's own
    counterpart to Phase C's Knowledge Graph -- see that package's own
    module docstring: "neither package imports from the other"). Same
    "purely a data holder, all aggregation happens in
    generate_dst_metadata() below" shape as CompilerMetadata/
    GraphMetadata above, one artifact over.

    The DST artifact (document_structure_tree.document_structure_tree.
    DocumentStructureTree, schema §2.2) folds metadata, provenance, and
    validation results into ONE value rather than the separate
    manifest/statistics/readiness-report/build-summary objects Phase B/C
    each produce -- so, unlike CompilerMetadata/GraphMetadata, this
    block carries the DST's own `artifact_metadata`/`validation_metadata`
    layers (schema §2.3/§2.5, already-serialized via their own
    `to_json()`) directly, rather than a separate manifest dict.
    `dst_chapter_fingerprint`/`final_dst_status` are still surfaced as
    their own top-level fields, mirroring `compiler_fingerprint`/
    `final_compiler_status` and `graph_fingerprint`/`final_graph_status`
    above, so a consumer scanning BuildMetadata for "the fingerprint" or
    "the status" of every Phase B/C/Milestone-5.1 artifact never needs to
    know each artifact's own internal shape to find them."""

    document_structure_tree_artifact_metadata: Optional[Dict[str, Any]]
    document_structure_tree_validation_metadata: Optional[Dict[str, Any]]
    dst_chapter_fingerprint: Optional[str]
    dst_node_count: Optional[int]
    final_dst_status: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_dst_metadata(
    *,
    document_structure_tree_artifact_metadata: Optional[Dict[str, Any]] = None,
    document_structure_tree_validation_metadata: Optional[Dict[str, Any]] = None,
    dst_chapter_fingerprint: Optional[str] = None,
    dst_node_count: Optional[int] = None,
    final_dst_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Milestone 5.2: read-only aggregation of the Document Structure
    Tree artifact Milestone 5.1 already produced this chapter. Every
    argument is already-computed, already-serialized data (`to_json()`
    output of `artifact_metadata`/`validation_metadata`, or a plain
    str/int already read off the DST artifact) -- this function performs
    no computation beyond wrapping them into one DSTMetadata dict, same
    "already in scope, no new computation" rule as
    generate_compiler_metadata()/generate_graph_metadata() above.

    Every argument defaults to None so this can be called even for a
    chapter where the DST was never (yet) built -- see
    finalize_build_metadata()'s own docstring for why that is the normal
    case at THIS function's own default call site."""
    metadata = DSTMetadata(
        document_structure_tree_artifact_metadata=document_structure_tree_artifact_metadata,
        document_structure_tree_validation_metadata=document_structure_tree_validation_metadata,
        dst_chapter_fingerprint=dst_chapter_fingerprint,
        dst_node_count=dst_node_count,
        final_dst_status=final_dst_status,
    )
    return metadata.to_dict()


# --------------------------------------------------------------------------
# BuildMetadata -- the top-level Phase E1 artifact
# --------------------------------------------------------------------------

@dataclass
class BuildMetadata:
    """The full Phase E1 BuildMetadata artifact -- CompilerMetadata +
    GraphMetadata + CompilationMetadata + ConfigurationMetadata +
    VersionMetadata, plus `generated_at`/`build_metadata_version`
    matching every earlier artifact's own convention. Purely a data
    holder; all aggregation happens in generate_build_metadata() below."""

    generated_at: str
    build_metadata_version: str
    compiler_metadata: Dict[str, Any]
    graph_metadata: Dict[str, Any]
    compilation_metadata: Dict[str, Any]
    configuration_metadata: Dict[str, Any]
    version_metadata: Dict[str, Any]
    # Milestone 5.2: additive, defaulted so any existing caller building a
    # BuildMetadata without DST awareness (or a chapter whose DST is not
    # yet available -- see finalize_build_metadata()'s own docstring) is
    # unaffected; an empty dict, exactly like generate_dst_metadata()'s
    # own all-None default shape, never a missing field.
    dst_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_build_metadata(
    *,
    compiler_metadata: Dict[str, Any],
    graph_metadata: Dict[str, Any],
    compilation_metadata: Dict[str, Any],
    configuration_metadata: Dict[str, Any],
    version_metadata: Dict[str, Any],
    dst_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E1 (+ Milestone 5.2's additive `dst_metadata`): assembles
    the already-computed sub-blocks into one BuildMetadata dict. Performs
    no computation of its own beyond wrapping them -- see module
    docstring's REUSE, DON'T RECOMPUTE section."""
    metadata = BuildMetadata(
        generated_at=datetime.now(timezone.utc).isoformat(),
        build_metadata_version=BUILD_METADATA_VERSION,
        compiler_metadata=compiler_metadata,
        graph_metadata=graph_metadata,
        compilation_metadata=compilation_metadata,
        configuration_metadata=configuration_metadata,
        version_metadata=version_metadata,
        dst_metadata=dst_metadata if dst_metadata is not None else {},
    )
    return metadata.to_dict()


# --------------------------------------------------------------------------
# Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def finalize_build_metadata(
    *,
    # Compiler-side (Phase B5.1-B5.3), already in scope in process_chapter().
    compiler_manifest: Optional[Dict[str, Any]],
    compiler_statistics: Optional[Dict[str, Any]],
    compiler_registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
    compiler_readiness_report: Optional[Dict[str, Any]],
    compiler_build_summary: Optional[Dict[str, Any]],
    final_compiler_status: Optional[str],
    # Knowledge-Graph-side (Phase C4.1-C4.3), already in scope.
    knowledge_graph_manifest: Optional[Dict[str, Any]],
    knowledge_graph_statistics: Optional[Dict[str, Any]],
    knowledge_graph_registry_fingerprints: Optional[Dict[str, str]],
    knowledge_graph_fingerprint: Optional[str],
    knowledge_graph_readiness_report: Optional[Dict[str, Any]],
    knowledge_graph_build_summary: Optional[Dict[str, Any]],
    final_graph_status: Optional[str],
    # Release-side (Phase D3), already in scope.
    release_status: Optional[str],
    # Operational (this chapter's own compilation run).
    pdf_path: Optional[str],
    compilation_start: Optional[datetime] = None,
    compilation_end: Optional[datetime] = None,
    processing_time_seconds: Optional[float] = None,
    use_vlm: bool = True,
    page_batch_size: Optional[int] = None,
    force: bool = False,
    # Milestone 5.2: Document Structure Tree side, already in scope
    # WHEN AVAILABLE -- unlike every argument above, the DST (Milestone
    # 5.1's own pipeline.py integration block) is built AFTER this
    # function's own call site in process_chapter() (DST construction
    # needs the fully-assembled `chapter_dict`, which itself is only
    # complete after Phase E1 already runs -- see pipeline.py's own
    # comments at each call site). Every DST argument therefore defaults
    # to None here, producing an all-None `dst_metadata` block exactly
    # like generate_dst_metadata()'s own default shape -- see
    # `attach_dst_metadata()` below for how pipeline.py fills this block
    # in once the DST actually exists, without re-running this function
    # or any of Phase E1's own aggregation a second time.
    document_structure_tree_artifact_metadata: Optional[Dict[str, Any]] = None,
    document_structure_tree_validation_metadata: Optional[Dict[str, Any]] = None,
    dst_chapter_fingerprint: Optional[str] = None,
    dst_node_count: Optional[int] = None,
    final_dst_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase E1's single pipeline.py integration point (mirrors
    compiler.finalize.finalize_compiler_build()'s and validation.
    release.finalize_release()'s own "one aggregation call" shape, one
    layer up). Must run AFTER validation.release.finalize_release() (so
    every Phase B-D3 artifact is available to aggregate) and is the LAST
    thing computed for this chapter before Chapter JSON is assembled --
    see pipeline.py's own comment at the call site.

    Read-only over every argument, and performs no new analysis, no new
    validation, and no new fingerprinting of its own beyond
    ConfigurationMetadata's single deterministic configuration
    fingerprint (see configuration_metadata.py) -- see module docstring's
    opening SCOPE paragraph.

    Returns `{"build_metadata": <dict>}`, ready to be handed to
    build_metadata.state.set_current_build_metadata() (this phase's own
    "store inside Build Metadata State" requirement, mirroring every
    earlier phase's own state-integration convention)."""
    compiler_metadata = generate_compiler_metadata(
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_build_summary,
        final_compiler_status=final_compiler_status,
    )
    graph_metadata = generate_graph_metadata(
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        registry_fingerprints=knowledge_graph_registry_fingerprints,
        graph_fingerprint=knowledge_graph_fingerprint,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_build_summary,
        final_graph_status=final_graph_status,
    )
    compilation_metadata = generate_compilation_metadata(
        pdf_path=pdf_path,
        compilation_start=compilation_start,
        compilation_end=compilation_end,
        processing_time_seconds=processing_time_seconds,
        use_vlm=use_vlm,
        page_batch_size=page_batch_size,
        force=force,
    )
    configuration_metadata = generate_configuration_metadata()
    version_metadata = generate_version_metadata(
        compiler_manifest=compiler_manifest,
        knowledge_graph_manifest=knowledge_graph_manifest,
        final_compiler_status=final_compiler_status,
        final_graph_status=final_graph_status,
        release_status=release_status,
    )
    dst_metadata = generate_dst_metadata(
        document_structure_tree_artifact_metadata=document_structure_tree_artifact_metadata,
        document_structure_tree_validation_metadata=document_structure_tree_validation_metadata,
        dst_chapter_fingerprint=dst_chapter_fingerprint,
        dst_node_count=dst_node_count,
        final_dst_status=final_dst_status,
    )

    build_metadata = generate_build_metadata(
        compiler_metadata=compiler_metadata,
        graph_metadata=graph_metadata,
        compilation_metadata=compilation_metadata,
        configuration_metadata=configuration_metadata,
        version_metadata=version_metadata,
        dst_metadata=dst_metadata,
    )
    return {"build_metadata": build_metadata}


def attach_dst_metadata(
    build_metadata: Dict[str, Any],
    *,
    dst_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Milestone 5.2: returns a NEW BuildMetadata dict with `dst_metadata`
    replaced by an already-computed (`generate_dst_metadata()`) block --
    never mutates `build_metadata` in place, mirroring
    `artifact_manager.manifest.attach_artifact_locations()`'s own
    "immutable record, return a new dict" convention one artifact type
    over.

    WHY THIS EXISTS, SEPARATELY FROM `finalize_build_metadata()`: the DST
    (Milestone 5.1) is built later in `pipeline.process_chapter()` than
    Phase E1's own `finalize_build_metadata()` call -- by the time this
    chapter's DST artifact exists, `finalize_build_metadata()` has
    already run and its result is already sitting in
    `build_metadata.state`. This function lets `pipeline.py` fill in the
    DST block once it actually has one, without re-running Phase E1's
    own compiler/graph/compilation/configuration/version aggregation a
    second time, and without moving or otherwise touching Milestone
    5.1's own frozen pipeline-integration block. Every other
    BuildMetadata field is passed through completely unchanged."""
    updated = dict(build_metadata)
    updated["dst_metadata"] = dst_metadata
    return updated