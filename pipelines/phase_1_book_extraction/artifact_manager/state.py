"""
artifact_manager/state.py — Phase F2: module-level "current build" state.

Reuses the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() idiom compiler/state.py established and every later
phase's own state.py has mirrored since (see runtime/state.py's own
module docstring for the same idiom applied one phase over). Applied
here to the one fact CompilerRuntime callers need after run()/resume()
returns: the Build this run/resume produced.

RUN-SCOPED, LIKE runtime/state.py -- NOT CHAPTER-SCOPED: a Build
describes one whole CompilerRuntime.run()/resume() call (see build.py),
so this state is set once per run/resume (by CompilerRuntime._execute(),
right before it returns), not once per chapter -- same rationale
runtime/state.py's own module docstring already gives for why runtime
state is run-scoped rather than chapter-scoped.

Not thread-safe / not concurrency-safe by design, same explicit note as
every module this mirrors.
"""
from __future__ import annotations

from typing import Optional

from .build import Build

_CURRENT_BUILD: Optional[Build] = None


def set_current_build(build: Build) -> None:
    """Called once by CompilerRuntime._execute() (runtime/runtime.py),
    immediately after this run's Build has been constructed, manifested,
    and persisted."""
    global _CURRENT_BUILD
    _CURRENT_BUILD = build


def get_current_build() -> Optional[Build]:
    """Returns the current/most-recently-produced Build, or None if no
    run()/resume() has ever completed in this process. Deliberately
    returns None rather than raising, for the same reason every other
    get_current_*() in this codebase does."""
    return _CURRENT_BUILD


def has_current_build() -> bool:
    """True once set_current_build() has been called and before the
    next reset_current_build() call."""
    return _CURRENT_BUILD is not None


def reset_current_build() -> None:
    """Clears this state back to its empty default. Safe to call even
    if nothing was ever set (idempotent), same as every other
    reset_*_state() in this codebase."""
    global _CURRENT_BUILD
    _CURRENT_BUILD = None
