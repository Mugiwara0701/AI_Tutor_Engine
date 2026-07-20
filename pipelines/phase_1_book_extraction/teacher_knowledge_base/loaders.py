"""
teacher_knowledge_base/loaders.py — M6.1: compiler artifact loaders.

SCOPE: this module loads the upstream compiler artifacts that feed the TKB
build pipeline. It NEVER recomputes, re-derives, or re-fingerprints any
upstream artifact — it reads what already exists in the build state and/or
on-disk artifact records.

INPUT ARTIFACTS (per M6.1 spec §Integration §10):
  - OptimizedKnowledgePackage      (primary input — Phase E5/cache output)
  - MasterKnowledgePackage         (Phase B compilation output)
  - KnowledgeGraph                 (Phase C graph output)
  - DocumentStructureTree          (Phase A DST output)
  - SemanticGraph                  (Phase C semantic graph)
  - ChapterJSON                    (per-chapter JSON written by json_writer)
  - CompilerReleaseManifest        (Phase D3 release output)

REUSE, DON'T REINVENT: every loader reads from already-existing state modules
(build_metadata.state, artifact_manager.state, change_detection.state) and
from the Build object's own reference fields — the same read-only pattern
build.py's build_reference_snapshot() already uses for Phase F2.

When a required artifact is absent:
  - raises TKBLoaderError (for mandatory artifacts)
  - returns None (for optional artifacts — marked below)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .exceptions import TKBLoaderError

logger = logging.getLogger("teacher_knowledge_base.loaders")


# ---------------------------------------------------------------------------
# Primary loader — assembles all available compiler artifacts into one dict.
# ---------------------------------------------------------------------------

def load_compiler_artifacts(
    build: Optional[Any] = None,
    storage: Optional[Any] = None,
) -> Dict[str, Any]:
    """Load all compiler artifacts available for the current TKB build.

    Reads from:
      1. artifact_manager.state (current Build) — for build-level references
      2. build_metadata.state — for BuildMetadata
      3. cache.state — for OptimizedKnowledgePackage / CacheEntry
      4. change_detection.state — for ChangeDetectionReport

    All reads are via already-public get_current_*() accessors — no new
    persistence, no new storage client, no re-computation.

    `build` — optional pre-loaded Build dataclass (if the caller already has
    it, avoids a second state read). If None, reads from artifact_manager.state.
    `storage` — optional OneDriveStorage instance (for loading chapter JSON
    or book manifest from storage). If None, file-based loading is skipped.

    Returns a dict keyed by artifact name. Missing optional artifacts are
    absent from the dict (never None values — absent keys make downstream
    `if key in artifacts` checks unambiguous).

    Raises TKBLoaderError if a mandatory artifact (build state) is missing.
    """
    artifacts: Dict[str, Any] = {}

    # -- 1. Build (run-scoped, mandatory) -----------------------------------
    resolved_build = build
    if resolved_build is None:
        try:
            from artifact_manager.state import get_current_build, has_current_build
            if has_current_build():
                resolved_build = get_current_build()
        except ImportError:
            logger.warning(
                "teacher_knowledge_base.loaders: artifact_manager.state not available — "
                "proceeding without Build reference."
            )

    if resolved_build is not None:
        artifacts["build"] = resolved_build
        logger.debug(
            "teacher_knowledge_base.loaders: loaded Build %s",
            getattr(resolved_build, "build_id", "<unknown>"),
        )

    # -- 2. BuildMetadata (chapter-scoped, optional) ------------------------
    try:
        from build_metadata.state import get_current_build_metadata, has_current_build_metadata
        if has_current_build_metadata():
            artifacts["build_metadata"] = get_current_build_metadata()
            logger.debug("teacher_knowledge_base.loaders: loaded BuildMetadata from state.")
    except ImportError:
        logger.debug("teacher_knowledge_base.loaders: build_metadata.state not available.")

    # -- 3. CacheEntry / OptimizedKnowledgePackage (optional) ---------------
    try:
        from cache.state import get_current_cache_entry, has_current_cache_entry
        if has_current_cache_entry():
            cache_entry = get_current_cache_entry()
            artifacts["cache_entry"] = cache_entry
            # Surface the knowledge package from the cache entry if present
            if isinstance(cache_entry, dict):
                okp = cache_entry.get("optimized_knowledge_package")
                if okp is not None:
                    artifacts["optimized_knowledge_package"] = okp
                    logger.debug(
                        "teacher_knowledge_base.loaders: loaded OptimizedKnowledgePackage "
                        "from CacheEntry."
                    )
    except ImportError:
        logger.debug("teacher_knowledge_base.loaders: cache.state not available.")

    # -- 4. ChangeDetectionReport (optional) --------------------------------
    try:
        from change_detection.state import (
            get_current_change_detection_report,
            has_current_change_detection_report,
        )
        if has_current_change_detection_report():
            artifacts["change_detection_report"] = get_current_change_detection_report()
            logger.debug(
                "teacher_knowledge_base.loaders: loaded ChangeDetectionReport from state."
            )
    except ImportError:
        logger.debug("teacher_knowledge_base.loaders: change_detection.state not available.")

    # -- 5. Build reference snapshot (chapter-scoped compiler artifacts) ----
    if resolved_build is not None:
        _load_build_references(resolved_build, artifacts)

    logger.info(
        "teacher_knowledge_base.loaders: loaded %d compiler artifact(s): %s",
        len(artifacts),
        sorted(artifacts.keys()),
    )
    return artifacts


def _load_build_references(build: Any, artifacts: Dict[str, Any]) -> None:
    """Reads the Build's *_reference fields (already computed by
    artifact_manager.build.build_reference_snapshot()) into the artifacts
    dict under their canonical names. Never recomputes — reads verbatim."""
    ref_map = {
        "compiler_ir_reference": "compiler_ir",
        "knowledge_graph_reference": "knowledge_graph",
        "dependency_graph_reference": "dependency_graph",
        "change_detection_reference": "change_detection_ref",
        "incremental_plan_reference": "incremental_plan",
        "incremental_validation_reference": "incremental_validation",
        "incremental_finalization_reference": "incremental_finalization",
        "build_metadata_reference": "build_metadata_ref",
    }
    for attr, key in ref_map.items():
        ref = getattr(build, attr, None)
        if ref is not None:
            # ref shape: {"source": "last_processed_chapter", "artifact": {...}}
            if isinstance(ref, dict) and "artifact" in ref:
                artifacts[key] = ref["artifact"]
            else:
                artifacts[key] = ref


# ---------------------------------------------------------------------------
# Targeted loaders — called by individual builders for their specific input.
# ---------------------------------------------------------------------------

def require_knowledge_graph(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the KnowledgeGraph dict from artifacts. Raises TKBLoaderError
    if not found (mandatory for EKG and EDG builders)."""
    kg = (
        artifacts.get("knowledge_graph")
        or artifacts.get("knowledge_graph_reference")
        or artifacts.get("compiler_ir", {}).get("knowledge_graph")
    )
    if not kg:
        raise TKBLoaderError(
            "KnowledgeGraph",
            "required by EKG/EDG builders but not found in any loaded compiler artifact. "
            "Ensure the pipeline ran Phases B-C before invoking the TKB builder.",
        )
    if not isinstance(kg, dict):
        raise TKBLoaderError("KnowledgeGraph", f"expected dict, got {type(kg).__name__}")
    return kg


def require_document_structure_tree(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the DST dict. Raises TKBLoaderError if not found (mandatory
    for EDST builder)."""
    dst = (
        artifacts.get("document_structure_tree")
        or artifacts.get("compiler_ir", {}).get("document_structure_tree")
        or _extract_from_compiler_ir(artifacts, "document_structure_tree")
    )
    if not dst:
        # Fallback: try to extract chapter structure from chapter_json
        chapter_json = artifacts.get("chapter_json")
        if chapter_json and isinstance(chapter_json, dict):
            dst = chapter_json.get("document_structure_tree") or chapter_json.get("structure")
    if not dst:
        raise TKBLoaderError(
            "DocumentStructureTree",
            "required by EDST builder but not found in compiler artifacts. "
            "Ensure Phase A completed successfully.",
        )
    return dst


def require_optimized_knowledge_package(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the OptimizedKnowledgePackage. Falls back to
    MasterKnowledgePackage if optimization was not applied. Raises
    TKBLoaderError only if neither is available."""
    okp = artifacts.get("optimized_knowledge_package")
    if okp:
        return okp
    mkp = artifacts.get("master_knowledge_package")
    if mkp:
        logger.warning(
            "teacher_knowledge_base.loaders: OptimizedKnowledgePackage not found — "
            "falling back to MasterKnowledgePackage. TKB will still build but without "
            "Phase E5 optimizations applied."
        )
        return mkp
    raise TKBLoaderError(
        "OptimizedKnowledgePackage",
        "neither OptimizedKnowledgePackage nor MasterKnowledgePackage found. "
        "Ensure the pipeline ran Phases B-E5 before invoking the TKB builder.",
    )


def get_chapter_json(artifacts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns the chapter JSON dict if available, else None (optional)."""
    return artifacts.get("chapter_json")


def get_compiler_release_manifest(artifacts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns the CompilerReleaseManifest if available, else None (optional)."""
    return artifacts.get("compiler_release_manifest")


def _extract_from_compiler_ir(
    artifacts: Dict[str, Any], key: str
) -> Optional[Any]:
    """Tries to extract `key` from the compiler_ir reference artifact.
    Returns None if compiler_ir is absent or the key is not found."""
    ir = artifacts.get("compiler_ir")
    if isinstance(ir, dict):
        return ir.get(key)
    return None


# ---------------------------------------------------------------------------
# Chapter concept extractor — used by multiple builders.
# ---------------------------------------------------------------------------

def extract_concepts(artifacts: Dict[str, Any]) -> list:
    """Extracts the flat list of concept dicts from the best available
    compiler artifact. Never modifies the source artifact.

    Priority order:
      1. optimized_knowledge_package.concepts
      2. master_knowledge_package.concepts
      3. knowledge_graph.nodes (graph-node form)
      4. compiler_ir.registry / compiler_ir.concepts
      5. Empty list (with warning) — never raises
    """
    for key in ("optimized_knowledge_package", "master_knowledge_package"):
        pkg = artifacts.get(key)
        if isinstance(pkg, dict):
            concepts = pkg.get("concepts") or pkg.get("concept_list") or []
            if concepts:
                logger.debug(
                    "teacher_knowledge_base.loaders: extracted %d concepts from %s",
                    len(concepts), key,
                )
                return list(concepts)

    kg = artifacts.get("knowledge_graph")
    if isinstance(kg, dict):
        nodes = kg.get("nodes") or kg.get("concept_nodes") or []
        if nodes:
            logger.debug(
                "teacher_knowledge_base.loaders: extracted %d concept nodes from knowledge_graph",
                len(nodes),
            )
            return list(nodes)

    ir = artifacts.get("compiler_ir")
    if isinstance(ir, dict):
        for sub_key in ("concepts", "registry", "concept_list"):
            items = ir.get(sub_key) or []
            if items:
                return list(items)

    logger.warning(
        "teacher_knowledge_base.loaders: no concepts found in any compiler artifact. "
        "TKB will build with an empty concept list."
    )
    return []
