"""
build_metadata/state.py — Phase E1: Build Metadata module-level state.

Follows the exact module-level-slot idiom already established by
compiler/state.py, knowledge_graph/state.py, and validation/state.py /
validation/release_state.py / validation/determinism_state.py: a single
"current chapter's BuildMetadata" slot, set once per chapter by
pipeline.py right after build_metadata.build.finalize_build_metadata()
finishes, read by any later in-process consumer via
get_current_build_metadata(), and cleared by
reset_build_metadata_state() before the next chapter's work starts so
one chapter's BuildMetadata never remains "current" while the next
chapter is being processed. No new architectural style is introduced --
this is the same pattern already established in this codebase, applied
to BuildMetadata.

Not thread-safe / not concurrency-safe by design, same as every other
"current chapter" state module in this codebase (this pipeline processes
one chapter at a time, in one process).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Current chapter's BuildMetadata dict, set once per chapter by
# pipeline.py after finalize_build_metadata() finishes and cleared by
# reset_build_metadata_state() before the next chapter's work starts.
# --------------------------------------------------------------------------
_CURRENT_BUILD_METADATA: Optional[Dict[str, Any]] = None


def set_current_build_metadata(build_metadata: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    build_metadata.build.finalize_build_metadata() finishes aggregating
    this chapter's BuildMetadata -- makes it part of this process's
    current-compilation state, reachable by any later in-process
    consumer via get_current_build_metadata(), without ever writing it
    into a compiler/graph registry or into Chapter JSON."""
    global _CURRENT_BUILD_METADATA
    _CURRENT_BUILD_METADATA = build_metadata


def get_current_build_metadata() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_build_metadata()'d dict, or
    None if none has been set yet in this process (or it has since been
    cleared by reset_build_metadata_state()). Deliberately returns None
    rather than raising: "no chapter's BuildMetadata has been generated
    yet in this process" is a normal, expected state, not an error
    condition."""
    return _CURRENT_BUILD_METADATA


def has_current_build_metadata() -> bool:
    """True once set_current_build_metadata() has been called and before
    the next reset_build_metadata_state() call -- a non-raising way to
    check availability before calling get_current_build_metadata()."""
    return _CURRENT_BUILD_METADATA is not None


def reset_build_metadata_state() -> None:
    """Clears the current chapter's BuildMetadata. Call once per
    chapter, alongside every other *_state.reset_*_state() call, before
    that chapter's own build_metadata generation happens (or, as
    pipeline.py does for every other per-chapter state module, at the
    top of process_chapter() before any per-chapter work starts) --
    never let one chapter's BuildMetadata remain "current" while the
    next chapter is being processed."""
    global _CURRENT_BUILD_METADATA
    _CURRENT_BUILD_METADATA = None