"""
teacher_knowledge_base/builder.py — M6.1: TKB public builder API.

This is the primary external-facing API for the Teacher Knowledge Base.
External callers (pipeline.py, runtime integrations) call:

    from teacher_knowledge_base.builder import build_teacher_knowledge_base
    result = build_teacher_knowledge_base(build=current_build, storage=storage)

INTEGRATION POINTS (per M6.1 spec §4):
  - Reads from: Artifact Manager (artifact_manager.state)
  - Reads from: Build Metadata (build_metadata.state)
  - Reads from: Cache (cache.state for OptimizedKnowledgePackage)
  - Reads from: Change Detection (change_detection.state)
  - Writes to: teacher_knowledge_base.state
  - Integrates with: Build Manifest (via registry.py)
  - Integrates with: Storage (via registry.py persistence)

BACKWARD COMPATIBILITY: this function never modifies any previous milestone's
artifacts, state, or APIs. It only reads from existing state modules and
writes to TKB-owned state.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .engine import run
from .exceptions import TKBBuildError
from .state import get_current_tkb_result, has_current_tkb_result

logger = logging.getLogger("teacher_knowledge_base.builder")


def build_teacher_knowledge_base(
    build: Optional[Any] = None,
    storage: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    direct_artifacts: Optional[Dict[str, Any]] = None,
) -> "TKBSerializationResult":  # noqa: F821
    """Build the complete TeacherKnowledgeBase artifact.

    This is the primary entry point for M6.1. Reads from existing compiler
    artifacts in state modules, executes the full TKB pipeline, and returns
    the serialized artifact.

    Parameters
    ----------
    build : Build, optional
        The current Build from artifact_manager. If None, read from
        artifact_manager.state.get_current_build().
    storage : OneDriveStorage, optional
        Storage instance for artifact persistence. If None, TKB is built
        in-memory only (useful for testing).
    config : dict, optional
        Build configuration. Supported keys:
          strict_validation (bool, default False):
            If True, raises TKBValidationError on any validation violation.
          enforce_determinism (bool, default True):
            If True, determinism checks are active.
          source_artifact_id (str):
            Override the source artifact ID used in TKB metadata.
          pipeline_version (str):
            Override the pipeline version string.
          chapter_ids (list):
            Override the list of chapter IDs (normally auto-resolved).

    Returns
    -------
    TKBSerializationResult
        Contains .artifact (TeacherKnowledgeBase), .artifact_dict,
        .canonical_json_str, .fingerprint, and .serialization_fingerprint.

    Raises
    ------
    TKBBuildError
        If a required pipeline stage fails.
    TKBValidationError
        If strict_validation=True and validation finds violations.
    """
    logger.info("teacher_knowledge_base.builder: starting TKB build.")
    try:
        result = run(build=build, storage=storage, config=config, direct_artifacts=direct_artifacts)
        logger.info(
            "teacher_knowledge_base.builder: TKB build complete. "
            "artifact_id=%s fingerprint=%s...",
            result.artifact.get_artifact_id(), result.fingerprint[:12],
        )
        return result
    except TKBBuildError:
        raise
    except Exception as exc:
        raise TKBBuildError(f"teacher_knowledge_base.builder: unexpected error: {exc}") from exc


def get_current_build_result() -> Optional["TKBSerializationResult"]:  # noqa: F821
    """Returns the result of the most recently completed TKB build, or None.
    Read-only accessor — mirrors artifact_manager.state.get_current_build()
    pattern."""
    if has_current_tkb_result():
        return get_current_tkb_result()
    return None
