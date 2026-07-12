"""
compiler_release/state.py — Phase F5: module-level "current run's
release manifest" state.

Reuses the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() idiom every other phase's own state.py in this codebase
already uses (see cache/state.py's own module docstring for the same
idiom applied one phase over).

RUN-SCOPED, LIKE artifact_manager/state.py, build_executor/state.py, AND
cache/state.py -- NOT CHAPTER-SCOPED: a CompilerReleaseManifest
describes one whole CompilerRuntime run()/resume() call, so this state
is set once per run/resume (by CompilerRuntime._record_release(),
immediately after Phase F1's RuntimeStatus, Phase F2's own Build, Phase
F3's own Execution Report, and Phase F4's own CacheEntry/
CacheValidationReport have all already been recorded), not once per
chapter.

ONE SLOT, NOT A PAIR -- unlike cache/state.py's own CacheEntry/
CacheValidationReport pair, Phase F5 has exactly one artifact, so this
module holds exactly one module-level slot with its own
set_current_*()/get_current_*()/has_current_*() trio, plus the shared
reset_current_release_manifest_state().

Not thread-safe / not concurrency-safe by design, same explicit note as
every module this mirrors.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_CURRENT_RELEASE_MANIFEST: Optional[Dict[str, Any]] = None


def set_current_release_manifest(manifest: Dict[str, Any]) -> None:
    """Called once by CompilerRuntime._record_release() (runtime/
    runtime.py), immediately after finalize_release() has returned and
    the manifest has been persisted."""
    global _CURRENT_RELEASE_MANIFEST
    _CURRENT_RELEASE_MANIFEST = manifest


def get_current_release_manifest() -> Optional[Dict[str, Any]]:
    """Returns the current/most-recently-produced CompilerReleaseManifest,
    or None if no run()/resume() has ever completed in this process (or
    Phase F5's own bookkeeping failed this run -- see runtime/runtime.py's
    own _record_release() "never raises" integration contract).
    Deliberately returns None rather than raising, for the same reason
    every other get_current_*() in this codebase does."""
    return _CURRENT_RELEASE_MANIFEST


def has_current_release_manifest() -> bool:
    """True once set_current_release_manifest() has been called and
    before the next reset_current_release_manifest_state() call."""
    return _CURRENT_RELEASE_MANIFEST is not None


def reset_current_release_manifest_state() -> None:
    """Clears this state back to its empty default. Safe to call even
    if nothing was ever set (idempotent), same as every other
    reset_*_state() in this codebase."""
    global _CURRENT_RELEASE_MANIFEST
    _CURRENT_RELEASE_MANIFEST = None
