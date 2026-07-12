"""
cache/state.py — Phase F4.1: module-level "current run's cache" state.

Reuses the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() idiom every other phase's own state.py in this
codebase already uses (see build_executor/state.py's own module
docstring for the same idiom applied one phase over).

RUN-SCOPED, LIKE artifact_manager/state.py AND build_executor/state.py
-- NOT CHAPTER-SCOPED: a CacheEntry and a CacheValidationReport each
describe one whole CompilerRuntime run()/resume() call, so this state
is set once per run/resume (by CompilerRuntime._record_cache(),
immediately after Phase F2's own Build and Phase F3's own Execution
Report have both been recorded), not once per chapter.

Two independent slots -- a CacheEntry and a CacheValidationReport --
each with its own set_current_*()/get_current_*()/has_current_*()/
reset_*_state() quartet, mirroring incremental_compilation_validation/
state.py's own "module-level slot pair" precedent one layer up.

Not thread-safe / not concurrency-safe by design, same explicit note
as every module this mirrors.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_CURRENT_CACHE_ENTRY: Optional[Dict[str, Any]] = None
_CURRENT_CACHE_VALIDATION_REPORT: Optional[Dict[str, Any]] = None


# -- CacheEntry ---------------------------------------------------------

def set_current_cache_entry(cache_entry: Dict[str, Any]) -> None:
    """Called once by CompilerRuntime._record_cache() (runtime/
    runtime.py), immediately after this run's fingerprint snapshot has
    been persisted (see cache.snapshot_store.persist_fingerprint_
    snapshot())."""
    global _CURRENT_CACHE_ENTRY
    _CURRENT_CACHE_ENTRY = cache_entry


def get_current_cache_entry() -> Optional[Dict[str, Any]]:
    """Returns the current/most-recently-produced CacheEntry, or None
    if no run()/resume() has ever completed in this process (or Phase
    F4.1's own bookkeeping failed this run -- see runtime/runtime.py's
    own _record_cache() "never raises" integration contract).
    Deliberately returns None rather than raising, for the same reason
    every other get_current_*() in this codebase does."""
    return _CURRENT_CACHE_ENTRY


def has_current_cache_entry() -> bool:
    """True once set_current_cache_entry() has been called and before
    the next reset_current_cache_state() call."""
    return _CURRENT_CACHE_ENTRY is not None


# -- CacheValidationReport ------------------------------------------------

def set_current_cache_validation_report(report: Dict[str, Any]) -> None:
    """Called once by CompilerRuntime._record_cache(), immediately
    after this run's CacheValidationReport has been generated (see
    cache.validation.validate_execution_against_cache())."""
    global _CURRENT_CACHE_VALIDATION_REPORT
    _CURRENT_CACHE_VALIDATION_REPORT = report


def get_current_cache_validation_report() -> Optional[Dict[str, Any]]:
    """Returns the current/most-recently-produced CacheValidationReport,
    or None under the exact same conditions get_current_cache_entry()
    documents."""
    return _CURRENT_CACHE_VALIDATION_REPORT


def has_current_cache_validation_report() -> bool:
    """True once set_current_cache_validation_report() has been called
    and before the next reset_current_cache_state() call."""
    return _CURRENT_CACHE_VALIDATION_REPORT is not None


# -- shared reset ---------------------------------------------------------

def reset_current_cache_state() -> None:
    """Clears both slots back to their empty default. Safe to call even
    if nothing was ever set (idempotent), same as every other
    reset_*_state() in this codebase. A single reset function for both
    slots (rather than two) mirrors incremental_compilation_
    validation/state.py's own "one reset for its own slot pair"
    precedent."""
    global _CURRENT_CACHE_ENTRY, _CURRENT_CACHE_VALIDATION_REPORT
    _CURRENT_CACHE_ENTRY = None
    _CURRENT_CACHE_VALIDATION_REPORT = None