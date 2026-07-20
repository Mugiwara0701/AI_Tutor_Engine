"""
teacher_knowledge_base/engine.py — M6.1/M6.2 (remediated)

Orchestrates the full TKB build pipeline.
Updated to use new TKBMetadata fields (tkb_id, chapter_id, etc.)
and compute content_hash + byte_size for serialization_metadata.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .artifact import build_artifact
from .context import TKBContext
from .exceptions import TKBBuildError, TKBBuilderError
from .loaders import load_compiler_artifacts
from .metadata import (
    build_tkb_metadata, build_tkb_compiler_info,
)
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
    run_start = time.monotonic()
    config = config or {}

    reset_all_tkb_state()

    # --- Load compiler artifacts ---
    logger.info("TKB engine: loading compiler artifacts.")
    try:
        if direct_artifacts is not None:
            compiler_artifacts = dict(direct_artifacts)
            state_artifacts = load_compiler_artifacts(build=build, storage=storage)
            for k, v in state_artifacts.items():
                if k not in compiler_artifacts:
                    compiler_artifacts[k] = v
        else:
            compiler_artifacts = load_compiler_artifacts(build=build, storage=storage)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: failed to load compiler artifacts: {exc}") from exc

    # --- Resolve metadata fields ---
    chapter_id = (
        config.get("chapter_id")
        or (config.get("chapter_ids") or [""])[0]
        or "unknown"
    )
    source_package_id = config.get("source_artifact_id") or _resolve_source_package_id(compiler_artifacts, build)
    chapter_number = int(config.get("chapter_number") or _resolve_chapter_number(compiler_artifacts))

    metadata = build_tkb_metadata(
        source_package_id=source_package_id,
        chapter_id=str(chapter_id),
        chapter_number=chapter_number,
        chapter_title=config.get("chapter_title") or _resolve_chapter_title(compiler_artifacts),
        subject=config.get("subject") or _resolve_field(compiler_artifacts, "subject"),
        book_title=config.get("book_title") or _resolve_field(compiler_artifacts, "book_title"),
        klass=config.get("klass") or _resolve_field(compiler_artifacts, "klass"),
        language=config.get("language") or "en",
        board=config.get("board") or _resolve_field(compiler_artifacts, "board"),
        status="READY",
        config=config,
    )
    logger.info("TKB engine: tkb_id=%s chapter=%s", metadata.tkb_id, chapter_id)

    compiler_information = build_tkb_compiler_info(compiler_artifacts)

    # --- Build context ---
    context = TKBContext(
        compiler_artifacts=compiler_artifacts,
        metadata=metadata,
        compiler_information=compiler_information,
        config=config,
    )

    # --- Execute pipeline stages ---
    stages = get_pipeline_stages()
    logger.info("TKB engine: executing %d pipeline stages.", len(stages))

    for stage in stages:
        t_start = time.monotonic()
        logger.info("TKB engine: [%s] starting.", stage.label)
        try:
            stage.build_fn(context)
            logger.info("TKB engine: [%s] completed in %.3fs.", stage.label, time.monotonic() - t_start)
        except (TKBBuilderError, TKBBuildError) as exc:
            if stage.required:
                raise TKBBuildError(f"TKB engine: required stage [{stage.label}] failed: {exc}") from exc
            else:
                context.diagnostics.add_warning(stage.name, f"Optional stage failed — skipping.", str(exc))
                logger.warning("TKB engine: [%s] failed (optional) — continuing. %s", stage.label, exc)
        except Exception as exc:
            if stage.required:
                raise TKBBuildError(f"TKB engine: required stage [{stage.label}] error: {exc}") from exc
            else:
                context.diagnostics.add_warning(stage.name, f"Unexpected error: {exc}")

    # --- Assemble artifact ---
    logger.info("TKB engine: assembling TeacherKnowledgeBase artifact.")
    try:
        artifact = build_artifact(context)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: artifact assembly failed: {exc}") from exc

    # --- Serialize ---
    logger.info("TKB engine: serializing.")
    try:
        result = serialize_artifact(artifact)
    except Exception as exc:
        raise TKBBuildError(f"TKB engine: serialization failed: {exc}") from exc

    # --- Register ---
    try:
        from .registry import register_tkb_artifact
        build_manifest = getattr(build, "build_manifest", None) if build else None
        register_tkb_artifact(result, build=build, storage=storage, build_manifest=build_manifest)
    except Exception as exc:
        logger.warning("TKB engine: registration failed (non-fatal): %s", exc)

    # --- Record state ---
    validation_output = context.get_output("validation") or {}
    passed = validation_output.get("status") in ("VALID", "VALID_WITH_WARNINGS")
    set_current_tkb_result(result)
    set_current_validation_passed(passed)

    total_time = round(time.monotonic() - run_start, 4)
    logger.info("TKB engine: complete. tkb_id=%s validation=%s time=%.3fs",
                metadata.tkb_id, validation_output.get("status"), total_time)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_source_package_id(artifacts: Dict[str, Any], build: Optional[Any]) -> str:
    if build:
        bid = getattr(build, "build_id", None)
        if bid:
            return str(bid)
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        pid = okp.get("manifest", {}).get("package_id") or okp.get("package_id")
        if pid:
            return str(pid)
    return "unknown"


def _resolve_chapter_number(artifacts: Dict[str, Any]) -> int:
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        meta = okp.get("metadata") or okp.get("manifest") or {}
        num = meta.get("chapter_number") or okp.get("chapter_number")
        if num is not None:
            return int(num)
    return 0


def _resolve_chapter_title(artifacts: Dict[str, Any]) -> str:
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        title = okp.get("chapter_title") or (okp.get("metadata") or {}).get("chapter_title")
        if title:
            return str(title)
    return ""


def _resolve_field(artifacts: Dict[str, Any], field: str) -> str:
    for key in ("optimized_knowledge_package", "master_knowledge_package", "build_metadata"):
        src = artifacts.get(key) or {}
        if isinstance(src, dict):
            val = src.get(field) or (src.get("metadata") or {}).get(field)
            if val:
                return str(val)
    return ""
