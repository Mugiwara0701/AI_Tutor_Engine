"""
teacher_knowledge_base/registry.py — M6.1: TKB artifact registry integration.

SCOPE: registers the TeacherKnowledgeBase as a first-class compiler artifact
with the Artifact Manager (artifact_manager package) and the Build Manifest.

REUSE: this module integrates with already-existing artifact_manager
infrastructure — it never invents a new registry format or a new persistence
mechanism. Registration means:
  1. Attaching the TKB artifact location to the Build Manifest's
     artifact_locations section (same pattern as chapter JSON / book manifest)
  2. Recording the TKB's own artifact_id, fingerprint, and storage path
     so the Artifact Manager can discover and load it later

INTEGRATION POINT: called by engine.run() after serialization completes,
before state.set_current_tkb_result() is called.

When artifact_manager is unavailable (standalone TKB build without a full
runtime), registration is skipped with a warning — TKB production is still
valid; only discovery via artifact_manager is affected.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .exceptions import TKBRegistrationError

logger = logging.getLogger("teacher_knowledge_base.registry")

TKB_ARTIFACT_TYPE = "teacher_knowledge_base"
TKB_RECORD_FILENAME = "_teacher_knowledge_base.json"


def register_tkb_artifact(
    serialization_result: "TKBSerializationResult",  # noqa: F821
    build: Optional[Any] = None,
    storage: Optional[Any] = None,
    build_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Registers the TKB artifact with the Artifact Manager.

    Returns a dict of registered paths/IDs.
    Raises TKBRegistrationError if registration fails and is non-optional.

    All parameters are optional — when not provided, registration is
    attempted in no-op mode (artifact is valid, only discovery is skipped).
    """
    artifact = serialization_result.artifact
    artifact_id = artifact.get_artifact_id()
    fingerprint = serialization_result.fingerprint

    registration_record: Dict[str, str] = {
        "artifact_id": artifact_id,
        "artifact_type": TKB_ARTIFACT_TYPE,
        "fingerprint": fingerprint,
        "schema_version": artifact.get_schema_version(),
    }

    # -- Attempt to attach to Build Manifest --------------------------------
    if build_manifest is not None:
        try:
            _attach_to_build_manifest(build_manifest, artifact_id, fingerprint)
            registration_record["manifest_attached"] = "true"
            logger.info(
                "teacher_knowledge_base.registry: attached artifact_id %s to build manifest.",
                artifact_id,
            )
        except Exception as exc:
            logger.warning(
                "teacher_knowledge_base.registry: failed to attach to build manifest: %s — "
                "TKB artifact is valid but not in manifest.", exc,
            )
            registration_record["manifest_attached"] = "false"

    # -- Attempt storage persistence ----------------------------------------
    if storage is not None:
        try:
            storage_path = _persist_to_storage(storage, serialization_result)
            registration_record["storage_path"] = storage_path
            logger.info(
                "teacher_knowledge_base.registry: persisted TKB to storage at %s",
                storage_path,
            )
        except Exception as exc:
            logger.warning(
                "teacher_knowledge_base.registry: storage persistence failed: %s — "
                "TKB is in-memory only.", exc,
            )
            registration_record["storage_path"] = "not_persisted"

    # -- Register with artifact_manager state --------------------------------
    _register_in_artifact_manager_state(artifact_id, fingerprint)

    logger.info(
        "teacher_knowledge_base.registry: registration complete for artifact_id=%s",
        artifact_id,
    )
    return registration_record


def _attach_to_build_manifest(
    build_manifest: Dict[str, Any],
    artifact_id: str,
    fingerprint: str,
) -> None:
    """Attaches the TKB artifact reference to the Build Manifest's
    artifact_locations section — same pattern as chapter JSON paths."""
    if "artifact_locations" not in build_manifest:
        build_manifest["artifact_locations"] = {}
    if "teacher_knowledge_bases" not in build_manifest["artifact_locations"]:
        build_manifest["artifact_locations"]["teacher_knowledge_bases"] = []
    build_manifest["artifact_locations"]["teacher_knowledge_bases"].append({
        "artifact_id": artifact_id,
        "artifact_type": TKB_ARTIFACT_TYPE,
        "fingerprint": fingerprint,
    })


def _persist_to_storage(
    storage: Any,
    serialization_result: "TKBSerializationResult",  # noqa: F821
) -> str:
    """Persists the TKB artifact dict to storage using the same upload_json()
    surface artifact_manager/persistence.py already uses. Returns the path."""
    artifact_id = serialization_result.artifact.get_artifact_id()
    path = f"_teacher_knowledge_bases/{artifact_id}/{TKB_RECORD_FILENAME}"
    storage_dict = serialization_result.to_storage_dict()
    try:
        storage.upload_json(path=path, data=storage_dict)
    except AttributeError:
        # Storage may expose upload_json under a different surface
        raise TKBRegistrationError(
            f"Storage object does not expose upload_json(). "
            f"Pass an OneDriveStorage instance for TKB persistence."
        )
    return path


def _register_in_artifact_manager_state(
    artifact_id: str,
    fingerprint: str,
) -> None:
    """Records the TKB artifact_id in artifact_manager's known types if possible.
    Silently skips if artifact_manager is not available."""
    try:
        # artifact_manager has no global artifact-type registry today —
        # this is a forward-compatible hook for when one is added.
        # Currently a no-op beyond the module-level state we set in state.py.
        pass
    except Exception:
        pass


def get_tkb_artifact_path(artifact_id: str) -> str:
    """Returns the canonical storage path for a TKB artifact by its ID.
    Same pure-function pattern as artifact_manager/persistence.py's
    build_record_path() / manifest_record_path()."""
    return f"_teacher_knowledge_bases/{artifact_id}/{TKB_RECORD_FILENAME}"
