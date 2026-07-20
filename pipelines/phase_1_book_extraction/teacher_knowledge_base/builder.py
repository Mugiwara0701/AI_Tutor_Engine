"""
teacher_knowledge_base/builder.py — M6.1/M6.2 (remediated)

Primary public entry point.
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

    Parameters
    ----------
    build : Build, optional
    storage : OneDriveStorage, optional
    config : dict, optional
        chapter_id, chapter_number, chapter_title, subject, book_title, klass, language, board,
        source_artifact_id, pipeline_version, strict_validation
    direct_artifacts : dict, optional
        Pre-loaded compiler artifacts. When provided, supplements state reads.

    Returns TKBSerializationResult.
    """
    logger.info("teacher_knowledge_base.builder: starting TKB build.")
    try:
        result = run(build=build, storage=storage, config=config, direct_artifacts=direct_artifacts)
        logger.info("teacher_knowledge_base.builder: complete. tkb_id=%s fingerprint=%s...",
                    result.artifact.get_tkb_id(), result.fingerprint[:12])
        return result
    except TKBBuildError:
        raise
    except Exception as exc:
        raise TKBBuildError(f"teacher_knowledge_base.builder: unexpected error: {exc}") from exc


def get_current_build_result() -> Optional["TKBSerializationResult"]:  # noqa: F821
    """Returns the result of the most recently completed TKB build, or None."""
    return get_current_tkb_result() if has_current_tkb_result() else None
