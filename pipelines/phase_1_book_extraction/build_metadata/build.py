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

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .compilation_metadata import generate_compilation_metadata
from .configuration_metadata import generate_configuration_metadata
from .version_metadata import generate_version_metadata

# M5.3 verification fix (wiring only, no behavior change): pipeline.py's
# own M5.2 integration block -- and that block's own comment -- import
# `generate_dst_metadata`/`attach_dst_metadata` from `build_metadata.build`,
# but these were implemented in the package's `__init__.py` instead. That
# mismatch means `from build_metadata.build import generate_dst_metadata,
# attach_dst_metadata` (pipeline.py's actual source line) raises
# ImportError as written. Re-exporting here (not moving the
# implementation, not changing DSTMetadata's shape or behavior) is the
# minimal fix that makes the existing, already-reviewed M5.2
# implementation actually importable the way its own call site expects.
from . import DSTMetadata, generate_dst_metadata, attach_dst_metadata  # noqa: F401

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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_build_metadata(
    *,
    compiler_metadata: Dict[str, Any],
    graph_metadata: Dict[str, Any],
    compilation_metadata: Dict[str, Any],
    configuration_metadata: Dict[str, Any],
    version_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase E1: assembles the five already-computed sub-blocks into one
    BuildMetadata dict. Performs no computation of its own beyond
    wrapping them -- see module docstring's REUSE, DON'T RECOMPUTE
    section."""
    metadata = BuildMetadata(
        generated_at=datetime.now(timezone.utc).isoformat(),
        build_metadata_version=BUILD_METADATA_VERSION,
        compiler_metadata=compiler_metadata,
        graph_metadata=graph_metadata,
        compilation_metadata=compilation_metadata,
        configuration_metadata=configuration_metadata,
        version_metadata=version_metadata,
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

    build_metadata = generate_build_metadata(
        compiler_metadata=compiler_metadata,
        graph_metadata=graph_metadata,
        compilation_metadata=compilation_metadata,
        configuration_metadata=configuration_metadata,
        version_metadata=version_metadata,
    )
    return {"build_metadata": build_metadata}