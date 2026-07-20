"""
teacher_knowledge_base/metadata.py — M6.1: TKB artifact metadata and
compiler_information blocks.

REUSE, DON'T RECOMPUTE: every field produced here is read from already-
computed upstream artifacts (Build, BuildMetadata, CompilerReleaseManifest,
VersionMetadata) — this module performs no new compilation, no new
fingerprinting of compiler content, and no new registry scanning. The one
new thing it computes is the TKB artifact's own deterministic ID
(uuid5-based, same namespace strategy as the rest of the codebase) and
its own schema_version marker.

NEVER PARTICIPATES IN TIMESTAMPS FOR IDENTITY: generated_at is a wall-clock
timestamp surfaced for human readability, never used in any identity or
fingerprint computation. All identity computation uses content-hash inputs
only — see _tkb_artifact_id() below.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Version marker — bump only if the SHAPE of the metadata block changes.
# --------------------------------------------------------------------------
TKB_METADATA_VERSION = "M6.1.0"
TKB_SCHEMA_VERSION = "1.0.0"

# UUID5 namespace for all TKB artifact IDs — deterministic, content-derived.
# Chosen to be unique to the TKB package; never reused by another artifact.
_TKB_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace, repurposed


def _tkb_artifact_id(
    source_artifact_id: str,
    pipeline_version: str,
    chapter_ids: list,
) -> str:
    """Deterministic UUID5 for this TKB artifact.

    Input is a stable canonical string built from the source artifact ID,
    pipeline version, and the sorted list of chapter IDs processed — so
    two builds from identical inputs always produce the same TKB ID, and
    any input change produces a different ID. Never depends on timestamps,
    random values, or memory addresses.
    """
    sorted_chapters = sorted(str(c) for c in chapter_ids)
    key = json.dumps(
        {
            "source": source_artifact_id,
            "pipeline_version": pipeline_version,
            "chapters": sorted_chapters,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_TKB_NAMESPACE, key))


@dataclass
class TKBMetadata:
    """Top-level metadata block of the TeacherKnowledgeBase artifact.

    Mirrors the shape every other Phase artifact's own metadata block
    carries in this codebase (artifact_id, schema_version, generated_at,
    source references) — nothing here is invented.
    """

    artifact_id: str
    schema_version: str
    metadata_version: str
    artifact_type: str
    generated_at: str            # ISO-8601 wall-clock, human-readable only
    source_artifact_id: str      # OptimizedKnowledgePackage or Build ID
    pipeline_version: str
    chapter_count: int
    chapter_ids: list
    build_id: Optional[str]
    release_status: Optional[str]
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TKBCompilerInformation:
    """compiler_information block — surfaces key compiler provenance fields
    from the upstream Build/BuildMetadata without duplicating their content.

    REUSE: every field here is read from an already-computed upstream
    artifact (BuildMetadata, CompilerReleaseManifest). Never recomputed.
    """

    compiler_version: Optional[str]
    graph_schema_version: Optional[str]
    release_status: Optional[str]
    build_id: Optional[str]
    chapter_count: int
    total_concepts: int
    optimization_applied: bool
    source_packages: list       # e.g. ["OptimizedKnowledgePackage", "MasterKnowledgePackage"]
    phase_versions: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_tkb_metadata(
    source_artifact_id: str,
    pipeline_version: str,
    chapter_ids: list,
    build_id: Optional[str] = None,
    release_status: Optional[str] = None,
) -> TKBMetadata:
    """Constructs the TKBMetadata block. Called once by pipeline.py at the
    start of the TKB build, before any builder stage runs — so the
    artifact_id is stable and available to all downstream stages via
    TKBContext."""
    artifact_id = _tkb_artifact_id(
        source_artifact_id=source_artifact_id,
        pipeline_version=pipeline_version,
        chapter_ids=chapter_ids,
    )
    return TKBMetadata(
        artifact_id=artifact_id,
        schema_version=TKB_SCHEMA_VERSION,
        metadata_version=TKB_METADATA_VERSION,
        artifact_type="TeacherKnowledgeBase",
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_artifact_id=source_artifact_id,
        pipeline_version=pipeline_version,
        chapter_count=len(chapter_ids),
        chapter_ids=sorted(str(c) for c in chapter_ids),
        build_id=build_id,
        release_status=release_status,
        description=(
            "Teacher Knowledge Base artifact — enriched DST, enriched Knowledge Graph, "
            "enriched Dependency Graph, Teaching Units, Concept Progression Templates, "
            "Curriculum Graph, Navigation, Runtime Indexes. Generated by M6.1 TKB Builder."
        ),
    )


def build_tkb_compiler_information(
    compiler_artifacts: Dict[str, Any],
    chapter_count: int,
    total_concepts: int,
) -> TKBCompilerInformation:
    """Constructs the TKBCompilerInformation block from already-loaded
    compiler artifact dicts. Never recomputes anything — reads only.

    `compiler_artifacts` is the dict produced by loaders.load_compiler_artifacts().
    """
    release_manifest = compiler_artifacts.get("compiler_release_manifest") or {}
    build_metadata = compiler_artifacts.get("build_metadata") or {}

    # Surface version markers verbatim from upstream artifacts
    compiler_version = (
        release_manifest.get("compiler_version")
        or build_metadata.get("compiler_metadata", {}).get("compiler_version")
    )
    graph_schema_version = (
        release_manifest.get("graph_schema_version")
        or build_metadata.get("graph_metadata", {}).get("graph_schema_version")
    )
    release_status = (
        release_manifest.get("release_status")
        or build_metadata.get("release_status")
    )
    build_id = (
        build_metadata.get("build_id")
        or release_manifest.get("build_id")
    )

    phase_versions: Dict[str, str] = {}
    if "version_metadata" in build_metadata:
        pv = build_metadata["version_metadata"].get("phase_versions", {})
        if isinstance(pv, dict):
            phase_versions = {str(k): str(v) for k, v in pv.items()}

    optimization_applied = "optimized_knowledge_package" in compiler_artifacts

    source_packages = []
    for key in ("optimized_knowledge_package", "master_knowledge_package",
                "knowledge_graph", "document_structure_tree",
                "semantic_graph", "chapter_json", "compiler_release_manifest"):
        if compiler_artifacts.get(key) is not None:
            source_packages.append(key)

    return TKBCompilerInformation(
        compiler_version=compiler_version,
        graph_schema_version=graph_schema_version,
        release_status=release_status,
        build_id=build_id,
        chapter_count=chapter_count,
        total_concepts=total_concepts,
        optimization_applied=optimization_applied,
        source_packages=source_packages,
        phase_versions=phase_versions,
    )
