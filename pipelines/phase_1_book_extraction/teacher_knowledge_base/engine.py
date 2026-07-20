"""
teacher_knowledge_base/engine.py — M6.1: TKB build engine.

The engine is the top-level orchestrator for a single TKB build run.
It:
  1. Builds the TKBContext (loads artifacts, constructs metadata)
  2. Runs each pipeline stage in order
  3. Assembles the final TeacherKnowledgeBase artifact
  4. Serializes and fingerprints the artifact
  5. Registers the artifact
  6. Records state

SINGLE ENTRY POINT: engine.run() — called by builder.build_teacher_knowledge_base()
which is the external-facing API.

ERROR HANDLING:
  - Required stages that fail raise TKBBuildError immediately.
  - Optional stages that fail record a warning and continue.
  - After all stages, validation errors are in the validation block.
  - Strict mode (config.strict_validation=True) raises on any validation error.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .artifact import build_artifact
from .context import TKBContext
from .exceptions import TKBBuildError, TKBBuilderError
from .loaders import load_compiler_artifacts, extract_concepts
from .metadata import build_tkb_metadata, build_tkb_compiler_information
from .pipeline import get_pipeline_stages
from .serialization import serialize_artifact
from .state import set_current_tkb_result, set_current_validation_passed, reset_all_tkb_state

logger = logging.getLogger("teacher_knowledge_base.engine")


def run(
    build: Optional[Any] = None,
    storage: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    direct_artifacts: Optional[Dict[str, Any]] = None,
) -> "TKBSerializationResult":  # noqa: F821
    """Runs the complete TKB build pipeline.

    Parameters:
      build   — optional Build object from artifact_manager.state. If None,
                the engine reads from artifact_manager.state.get_current_build().
      storage — optional OneDriveStorage for persistence. If None, the TKB
                is built in-memory only (no storage persistence).
      config  — optional build configuration:
                  strict_validation: bool (default False)
                  enforce_determinism: bool (default True)
                  source_artifact_id: str (override — defaults to build.build_id)
                  pipeline_version: str (override — defaults to TKB_ARTIFACT_VERSION)
                  chapter_ids: list (override — normally auto-resolved)
      direct_artifacts — optional pre-loaded compiler artifacts dict. When provided,
                these artifacts are used INSTEAD of loading from module-level state.
                Useful for testing and standalone builds. Keys match loaders.py output
                (e.g. 'knowledge_graph', 'document_structure_tree', etc.)

    Returns TKBSerializationResult — the built, serialized, registered artifact.
    Raises TKBBuildError if any required stage fails.
    """
    run_start = time.monotonic()
    config = config or {}

    # -- Reset state --------------------------------------------------------
    reset_all_tkb_state()

    # -- Load compiler artifacts --------------------------------------------
    logger.info("TKB engine: loading compiler artifacts.")
    try:
        if direct_artifacts is not None:
            # Direct injection — use provided dict, supplemented by state reads
            compiler_artifacts = dict(direct_artifacts)
            state_artifacts = load_compiler_artifacts(build=build, storage=storage)
            # Only add state artifacts that are not already in direct_artifacts
            for k, v in state_artifacts.items():
                if k not in compiler_artifacts:
                    compiler_artifacts[k] = v
        else:
            compiler_artifacts = load_compiler_artifacts(build=build, storage=storage)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: failed to load compiler artifacts: {exc}") from exc

    # -- Determine chapter IDs and source artifact ID -----------------------
    chapter_ids = _resolve_chapter_ids(compiler_artifacts, config)
    source_artifact_id = _resolve_source_artifact_id(compiler_artifacts, config, build)
    pipeline_version = config.get("pipeline_version", "M6.1.0")

    build_obj = compiler_artifacts.get("build") or build
    build_id = getattr(build_obj, "build_id", None) if build_obj else None
    release_status = _resolve_release_status(compiler_artifacts)

    # -- Build TKBMetadata --------------------------------------------------
    metadata = build_tkb_metadata(
        source_artifact_id=source_artifact_id,
        pipeline_version=pipeline_version,
        chapter_ids=chapter_ids,
        build_id=build_id,
        release_status=release_status,
    )
    logger.info("TKB engine: artifact_id=%s", metadata.artifact_id)

    # -- Build TKBCompilerInformation ---------------------------------------
    concepts = extract_concepts(compiler_artifacts)
    compiler_information = build_tkb_compiler_information(
        compiler_artifacts=compiler_artifacts,
        chapter_count=len(chapter_ids),
        total_concepts=len(concepts),
    )

    # -- Construct TKBContext -----------------------------------------------
    context = TKBContext(
        compiler_artifacts=compiler_artifacts,
        metadata=metadata,
        compiler_information=compiler_information,
        config=config,
    )

    # -- Execute pipeline stages -------------------------------------------
    stages = get_pipeline_stages()
    logger.info("TKB engine: executing %d pipeline stages.", len(stages))

    for stage in stages:
        stage_start = time.monotonic()
        logger.info("TKB engine: [%s] starting.", stage.label)
        try:
            stage.build_fn(context)
            logger.info(
                "TKB engine: [%s] completed in %.3fs.",
                stage.label, time.monotonic() - stage_start,
            )
        except (TKBBuilderError, TKBBuildError) as exc:
            if stage.required:
                raise TKBBuildError(
                    f"TKB engine: required stage [{stage.label}] failed: {exc}"
                ) from exc
            else:
                context.diagnostics.add_warning(
                    stage.name,
                    f"Optional stage [{stage.label}] failed — skipping.",
                    str(exc),
                )
                logger.warning(
                    "TKB engine: [%s] failed (optional) — continuing. %s",
                    stage.label, exc,
                )
        except Exception as exc:
            if stage.required:
                raise TKBBuildError(
                    f"TKB engine: required stage [{stage.label}] raised unexpected error: {exc}"
                ) from exc
            else:
                context.diagnostics.add_warning(stage.name, f"Unexpected error: {exc}")
                logger.warning("TKB engine: [%s] unexpected error (optional) — continuing.", stage.label)

    # -- Assemble final artifact --------------------------------------------
    logger.info("TKB engine: assembling final TeacherKnowledgeBase artifact.")
    try:
        artifact = build_artifact(context)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: artifact assembly failed: {exc}") from exc

    # -- Serialize ----------------------------------------------------------
    logger.info("TKB engine: serializing artifact.")
    from .serialization import serialize_artifact
    try:
        result = serialize_artifact(artifact)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: serialization failed: {exc}") from exc

    # -- Register -----------------------------------------------------------
    logger.info("TKB engine: registering artifact.")
    try:
        from .registry import register_tkb_artifact
        build_manifest = None
        if build_obj is not None:
            build_manifest = getattr(build_obj, "build_manifest", None)
        register_tkb_artifact(result, build=build_obj, storage=storage, build_manifest=build_manifest)
    except Exception as exc:
        logger.warning("TKB engine: registration failed (non-fatal): %s", exc)

    # -- Record state -------------------------------------------------------
    validation_output = context.get_output("validation") or {}
    passed = validation_output.get("passed", True)
    set_current_tkb_result(result)
    set_current_validation_passed(passed)

    total_time = round(time.monotonic() - run_start, 4)
    logger.info(
        "TKB engine: build complete. artifact_id=%s validation_passed=%s total_time=%.3fs",
        metadata.artifact_id, passed, total_time,
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_chapter_ids(
    compiler_artifacts: Dict[str, Any],
    config: Dict[str, Any],
) -> List[str]:
    """Resolves the list of chapter IDs from compiler artifacts."""
    # From config override
    if "chapter_ids" in config:
        return list(config["chapter_ids"])

    # From OptimizedKnowledgePackage
    okp = compiler_artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        chapters = okp.get("chapter_ids") or okp.get("chapters") or []
        if chapters:
            return [str(c) for c in chapters]

    # From KnowledgeGraph nodes
    from .loaders import extract_concepts
    concepts = extract_concepts(compiler_artifacts)
    chapter_set = set()
    for c in concepts:
        if isinstance(c, dict):
            ch = c.get("chapter_id") or c.get("chapter")
            if ch:
                chapter_set.add(str(ch))
    if chapter_set:
        return sorted(chapter_set)

    # From build metadata
    bm = compiler_artifacts.get("build_metadata") or {}
    if isinstance(bm, dict):
        compilation = bm.get("compilation_metadata") or {}
        chapters = compilation.get("chapter_ids") or []
        if chapters:
            return [str(c) for c in chapters]

    logger.warning("TKB engine: could not resolve chapter IDs — using ['unknown'].")
    return ["unknown"]


def _resolve_source_artifact_id(
    compiler_artifacts: Dict[str, Any],
    config: Dict[str, Any],
    build: Optional[Any],
) -> str:
    """Resolves the source artifact ID for the TKB metadata."""
    if "source_artifact_id" in config:
        return str(config["source_artifact_id"])
    # From build
    if build is not None:
        bid = getattr(build, "build_id", None)
        if bid:
            return str(bid)
    # From build in artifacts
    build_in_artifacts = compiler_artifacts.get("build")
    if build_in_artifacts is not None:
        bid = getattr(build_in_artifacts, "build_id", None)
        if bid:
            return str(bid)
    # From OKP
    okp = compiler_artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        aid = okp.get("artifact_id") or okp.get("package_id")
        if aid:
            return str(aid)
    return "unknown"


def _resolve_release_status(compiler_artifacts: Dict[str, Any]) -> Optional[str]:
    for key in ("compiler_release_manifest", "build_metadata"):
        artifact = compiler_artifacts.get(key) or {}
        if isinstance(artifact, dict):
            status = artifact.get("release_status")
            if status:
                return str(status)
    return None
