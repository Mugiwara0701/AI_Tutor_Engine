"""
compiler/state.py — Phase B1 architectural refinement: RegistryManager
ownership and lifecycle.

BEFORE this refinement: pipeline.py's process_chapter() built a
RegistryManager, populated it via populate_registries(), and then let it
fall out of scope at the end of the function -- a real symbol table that
existed for a few lines and was then discarded, of no use to any later
phase without pipeline.py itself being changed to return or thread it
through.

AFTER this refinement: the populated RegistryManager for the
chapter currently (or most recently) compiled in this process is held
here, as this module's "current compilation state" -- the same
established idiom modules/semantic_processor.py already uses for
per-chapter state (_CURRENT_LANGUAGE / reset_chapter_state()): a
module-level slot, set once per chapter by pipeline.py, read by any
later phase that needs it, and reset before the next chapter starts so
state never leaks across chapters. No new architectural style is
introduced -- this is the same pattern already established in this
codebase, applied to RegistryManager.

OWNERSHIP / LIFECYCLE (read this before using get_current_registry_manager()
from a later phase):

  1. pipeline.py's process_chapter() calls reset_registry_state() at the
     same point it already calls semantic_processor.reset_chapter_state()
     -- before any per-chapter work starts -- so a failed or skipped
     chapter never leaves a stale manager from the previous chapter
     visible as "current."
  2. process_chapter() builds a fresh RegistryManager (via
     compiler.registries.create_registry_manager()), populates it (via
     populate_registries()), and calls set_current_registry_manager() on
     it once population is complete -- this is the ONLY place anything
     is written into this module's state.
  3. From that point until the next reset_registry_state() call (i.e.
     until the next chapter starts processing, or the process exits),
     get_current_registry_manager() returns that exact, fully-populated
     RegistryManager -- the same instance, not a copy -- to any caller in
     this process. This is what lets a later phase (B1b enrichment, B2
     relationship generation, B3 cross-link resolution, Phase C Knowledge
     Graph construction, ...) consume this chapter's registries without
     rebuilding them from the Chapter JSON, PROVIDED that phase runs
     in-process, immediately after process_chapter() returns for that
     chapter (e.g. from within the same process_all_pdfs() loop
     iteration) -- exactly the shape those later phases are expected to
     take, since none of them exist yet.
  4. A consumer that needs a chapter's registries to outlive that
     lifetime (a separate process, or after the next chapter has already
     reset this state) must capture the RegistryManager itself (e.g. via
     get_current_registry_manager()) before the next chapter starts, or
     persist it (RegistryManager.serialize()/to_json(), already provided
     by B0) and reload it later (RegistryManager.deserialize()/from_json()).
     This module intentionally does not attempt to solve that broader
     persistence question -- doing so would be new compiler scope beyond
     Phase B1's population-only mandate.

Not thread-safe / not concurrency-safe by design, same as
semantic_processor's equivalent module-level state: this pipeline
processes one chapter at a time, in one process, exactly like every
other piece of "current chapter" state already in this codebase.

PHASE B4 ADDITION (Validation & Integrity Pass): the same module-level-
slot idiom is reused, unmodified, for the compiler validation report
compiler/validation.py's validate_compiler_state() produces --
set_current_validation_report() / get_current_validation_report() /
has_current_validation_report() below are the exact same shape as their
_CURRENT_REGISTRY_MANAGER equivalents above, and reset_registry_state()
now clears both slots together (still the one function pipeline.py calls
once per chapter) so a validation report never survives past the chapter
it was computed for. This is additive only: nothing above this point was
changed, no existing function's signature or behavior changed.

PHASE B5.1 ADDITION (Compiler Manifest & Statistics): the same
module-level-slot idiom is reused again, unmodified, for the two new
Phase B5.1 artifacts compiler/build.py's generate_compiler_manifest() /
generate_compiler_statistics() produce -- set_current_compiler_manifest()
/ get_current_compiler_manifest() / has_current_compiler_manifest() and
set_current_compiler_statistics() / get_current_compiler_statistics() /
has_current_compiler_statistics() below are the exact same shape as
_CURRENT_VALIDATION_REPORT's own get/set/has trio above, and
reset_registry_state() now clears all four slots together (still the one
function pipeline.py calls once per chapter) so neither artifact ever
survives past the chapter it was computed for. This is additive only:
nothing above this point was changed, no existing function's signature
or behavior changed.

PHASE B5.2 ADDITION (Compiler Fingerprints & Readiness): the same
module-level-slot idiom is reused a third time, unmodified, for the
three new Phase B5.2 artifacts compiler/fingerprints.py's
generate_registry_fingerprints() / generate_compiler_fingerprint() /
generate_compiler_readiness_report() produce -- set_current_registry_
fingerprints() / get_current_registry_fingerprints() / has_current_
registry_fingerprints(), set_current_compiler_fingerprint() / get_
current_compiler_fingerprint() / has_current_compiler_fingerprint(), and
set_current_compiler_readiness_report() / get_current_compiler_
readiness_report() / has_current_compiler_readiness_report() below are
the exact same shape as _CURRENT_COMPILER_MANIFEST's own get/set/has
trio above, and reset_registry_state() now clears all seven slots
together (still the one function pipeline.py calls once per chapter) so
none of these three artifacts ever survives past the chapter it was
computed for. This is additive only: nothing above this point was
changed, no existing function's signature or behavior changed.

PHASE B5.3 ADDITION (Compiler Finalization & Phase B Completion): the
same module-level-slot idiom is reused a fourth time, unmodified, for the
two new Phase B5.3 artifacts compiler/finalize.py's
generate_compiler_build_summary() / determine_final_compiler_status()
produce -- set_current_compiler_build_summary() / get_current_compiler_
build_summary() / has_current_compiler_build_summary() and
set_current_final_compiler_status() / get_current_final_compiler_status()
/ has_current_final_compiler_status() below are the exact same shape as
_CURRENT_COMPILER_READINESS_REPORT's own get/set/has trio above, and
reset_registry_state() now clears all nine slots together (still the one
function pipeline.py calls once per chapter) so neither artifact ever
survives past the chapter it was computed for. This is additive only:
nothing above this point was changed, no existing function's signature
or behavior changed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .registry_manager import RegistryManager

# --------------------------------------------------------------------------
# Current chapter's populated RegistryManager, set once per chapter by
# pipeline.py after populate_registries() finishes and cleared by
# reset_registry_state() before the next chapter's work starts. See
# module docstring for the full ownership/lifecycle contract.
# --------------------------------------------------------------------------
_CURRENT_REGISTRY_MANAGER: Optional[RegistryManager] = None


def set_current_registry_manager(manager: RegistryManager) -> None:
    """Called once per chapter by pipeline.py, right after
    populate_registries() finishes populating `manager` -- this is what
    promotes it from "a local variable about to go out of scope" to "the
    compiler's internal compilation state" a later phase can consume."""
    global _CURRENT_REGISTRY_MANAGER
    _CURRENT_REGISTRY_MANAGER = manager


def get_current_registry_manager() -> Optional[RegistryManager]:
    """Returns the most recently set_current_registry_manager()'d
    RegistryManager, or None if none has been set yet in this process (or
    it has since been cleared by reset_registry_state()). Returns the
    same instance every time -- never a copy -- so mutating it (e.g. a
    later phase inserting enrichment fields into an existing item) is
    visible to every other holder of the reference. Deliberately returns
    None rather than raising: "no chapter has been compiled yet in this
    process" is a normal, expected state (e.g. right after import,
    before process_chapter() has run at all), not an error condition."""
    return _CURRENT_REGISTRY_MANAGER


def has_current_registry_manager() -> bool:
    """True once set_current_registry_manager() has been called and
    before the next reset_registry_state() -- a non-raising way to check
    availability before calling get_current_registry_manager()."""
    return _CURRENT_REGISTRY_MANAGER is not None


def reset_registry_state() -> None:
    """Clears the current RegistryManager (and, since Phase B4, the
    current validation report -- see module docstring's PHASE B4
    ADDITION note; and, since Phase B5.1, the current compiler manifest
    and compiler statistics -- see module docstring's PHASE B5.1
    ADDITION note; and, since Phase B5.2, the current registry
    fingerprints, compiler fingerprint, and compiler readiness report --
    see module docstring's PHASE B5.2 ADDITION note). Call once per
    chapter, alongside semantic_processor.reset_chapter_state(), before
    any per-chapter work starts -- never let one chapter's registries (or
    validation report, manifest, statistics, fingerprints, readiness
    report) remain "current" while the next chapter is being processed,
    mirroring exactly why reset_chapter_state() exists for the
    equation-semantics cache."""
    global _CURRENT_REGISTRY_MANAGER, _CURRENT_VALIDATION_REPORT
    global _CURRENT_COMPILER_MANIFEST, _CURRENT_COMPILER_STATISTICS
    global _CURRENT_REGISTRY_FINGERPRINTS, _CURRENT_COMPILER_FINGERPRINT
    global _CURRENT_COMPILER_READINESS_REPORT
    global _CURRENT_COMPILER_BUILD_SUMMARY, _CURRENT_FINAL_COMPILER_STATUS
    _CURRENT_REGISTRY_MANAGER = None
    _CURRENT_VALIDATION_REPORT = None
    _CURRENT_COMPILER_MANIFEST = None
    _CURRENT_COMPILER_STATISTICS = None
    _CURRENT_REGISTRY_FINGERPRINTS = None
    _CURRENT_COMPILER_FINGERPRINT = None
    _CURRENT_COMPILER_READINESS_REPORT = None
    _CURRENT_COMPILER_BUILD_SUMMARY = None
    _CURRENT_FINAL_COMPILER_STATUS = None


# --------------------------------------------------------------------------
# Phase B4: current chapter's compiler validation report, set once per
# chapter by pipeline.py after validate_compiler_state() finishes and
# cleared by reset_registry_state() above, alongside the registry
# manager. Exact same idiom as _CURRENT_REGISTRY_MANAGER above -- see
# module docstring's PHASE B4 ADDITION note.
# --------------------------------------------------------------------------
_CURRENT_VALIDATION_REPORT: Optional[Dict[str, Any]] = None


def set_current_validation_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    validate_compiler_state() finishes validating this chapter's
    RegistryManager -- this is what makes the validation report part of
    the compiler state (task's own "the validation report should become
    part of the compiler state" requirement), reachable by any later
    in-process phase via get_current_validation_report(), without
    threading it through every function signature and without ever
    writing it into `manager` itself or into Chapter JSON."""
    global _CURRENT_VALIDATION_REPORT
    _CURRENT_VALIDATION_REPORT = report


def get_current_validation_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_validation_report()'d report
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_registry_state()). Deliberately returns
    None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_VALIDATION_REPORT


def has_current_validation_report() -> bool:
    """True once set_current_validation_report() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_VALIDATION_REPORT is not None


# --------------------------------------------------------------------------
# Phase B5.1: current chapter's compiler manifest, set once per chapter by
# pipeline.py after generate_compiler_manifest() finishes and cleared by
# reset_registry_state() above, alongside the registry manager and
# validation report. Exact same idiom as _CURRENT_VALIDATION_REPORT above
# -- see module docstring's PHASE B5.1 ADDITION note.
# --------------------------------------------------------------------------
_CURRENT_COMPILER_MANIFEST: Optional[Dict[str, Any]] = None


def set_current_compiler_manifest(manifest: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.build.generate_compiler_manifest() finishes describing this
    chapter's compiler build -- this is what makes the manifest part of
    the compiler state (task's own "the manifest belongs to Compiler
    State" requirement), reachable by any later in-process phase via
    get_current_compiler_manifest(), without threading it through every
    function signature and without ever writing it into `manager` itself
    or into Chapter JSON."""
    global _CURRENT_COMPILER_MANIFEST
    _CURRENT_COMPILER_MANIFEST = manifest


def get_current_compiler_manifest() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_compiler_manifest()'d
    manifest dict, or None if none has been set yet in this process (or
    it has since been cleared by reset_registry_state()). Deliberately
    returns None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_COMPILER_MANIFEST


def has_current_compiler_manifest() -> bool:
    """True once set_current_compiler_manifest() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_COMPILER_MANIFEST is not None


# --------------------------------------------------------------------------
# Phase B5.1: current chapter's compiler statistics, set once per chapter
# by pipeline.py after generate_compiler_statistics() finishes and
# cleared by reset_registry_state() above, alongside the registry
# manager, validation report, and compiler manifest. Exact same idiom as
# _CURRENT_VALIDATION_REPORT above -- see module docstring's PHASE B5.1
# ADDITION note.
# --------------------------------------------------------------------------
_CURRENT_COMPILER_STATISTICS: Optional[Dict[str, Any]] = None


def set_current_compiler_statistics(statistics: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.build.generate_compiler_statistics() finishes summarizing
    this chapter's compiler build -- makes the statistics part of the
    compiler state (task's own "store compiler statistics" requirement),
    reachable by any later in-process phase via
    get_current_compiler_statistics(), without ever writing it into
    `manager` itself or into Chapter JSON."""
    global _CURRENT_COMPILER_STATISTICS
    _CURRENT_COMPILER_STATISTICS = statistics


def get_current_compiler_statistics() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_compiler_statistics()'d
    statistics dict, or None if none has been set yet in this process (or
    it has since been cleared by reset_registry_state()). Deliberately
    returns None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_COMPILER_STATISTICS


def has_current_compiler_statistics() -> bool:
    """True once set_current_compiler_statistics() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_COMPILER_STATISTICS is not None


# --------------------------------------------------------------------------
# Phase B5.2: current chapter's registry fingerprints, set once per
# chapter by pipeline.py after generate_registry_fingerprints() (via
# generate_compiler_fingerprints()) finishes and cleared by
# reset_registry_state() above, alongside every other current-chapter
# artifact. Exact same idiom as _CURRENT_COMPILER_MANIFEST above -- see
# module docstring's PHASE B5.2 ADDITION note.
# --------------------------------------------------------------------------
_CURRENT_REGISTRY_FINGERPRINTS: Optional[Dict[str, str]] = None


def set_current_registry_fingerprints(fingerprints: Dict[str, str]) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.fingerprints.generate_compiler_fingerprints() finishes
    fingerprinting this chapter's registries -- makes the per-registry
    fingerprints part of the compiler state (task's own "store inside
    Compiler State" requirement), reachable by any later in-process phase
    via get_current_registry_fingerprints(), without ever writing them
    into `manager` itself or into Chapter JSON."""
    global _CURRENT_REGISTRY_FINGERPRINTS
    _CURRENT_REGISTRY_FINGERPRINTS = fingerprints


def get_current_registry_fingerprints() -> Optional[Dict[str, str]]:
    """Returns the most recently set_current_registry_fingerprints()'d
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_registry_state()). Deliberately returns
    None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_REGISTRY_FINGERPRINTS


def has_current_registry_fingerprints() -> bool:
    """True once set_current_registry_fingerprints() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_REGISTRY_FINGERPRINTS is not None


# --------------------------------------------------------------------------
# Phase B5.2: current chapter's compiler fingerprint, set once per
# chapter by pipeline.py after generate_compiler_fingerprint() (via
# generate_compiler_fingerprints()) finishes and cleared by
# reset_registry_state() above. Exact same idiom as
# _CURRENT_REGISTRY_FINGERPRINTS above.
# --------------------------------------------------------------------------
_CURRENT_COMPILER_FINGERPRINT: Optional[str] = None


def set_current_compiler_fingerprint(fingerprint: str) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.fingerprints.generate_compiler_fingerprints() finishes
    deriving this chapter's single compiler fingerprint -- makes it part
    of the compiler state, reachable by any later in-process phase via
    get_current_compiler_fingerprint(), without ever writing it into
    `manager` itself or into Chapter JSON."""
    global _CURRENT_COMPILER_FINGERPRINT
    _CURRENT_COMPILER_FINGERPRINT = fingerprint


def get_current_compiler_fingerprint() -> Optional[str]:
    """Returns the most recently set_current_compiler_fingerprint()'d
    digest string, or None if none has been set yet in this process (or
    it has since been cleared by reset_registry_state()). Deliberately
    returns None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_COMPILER_FINGERPRINT


def has_current_compiler_fingerprint() -> bool:
    """True once set_current_compiler_fingerprint() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_COMPILER_FINGERPRINT is not None


# --------------------------------------------------------------------------
# Phase B5.2: current chapter's compiler readiness report, set once per
# chapter by pipeline.py after generate_compiler_readiness_report() (via
# generate_compiler_fingerprints()) finishes and cleared by
# reset_registry_state() above. Exact same idiom as
# _CURRENT_REGISTRY_FINGERPRINTS above.
# --------------------------------------------------------------------------
_CURRENT_COMPILER_READINESS_REPORT: Optional[Dict[str, Any]] = None


def set_current_compiler_readiness_report(report: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.fingerprints.generate_compiler_fingerprints() finishes
    assessing this chapter's readiness -- makes the readiness report part
    of the compiler state, reachable by any later in-process phase via
    get_current_compiler_readiness_report(), without ever writing it into
    `manager` itself or into Chapter JSON."""
    global _CURRENT_COMPILER_READINESS_REPORT
    _CURRENT_COMPILER_READINESS_REPORT = report


def get_current_compiler_readiness_report() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_compiler_readiness_report()'d
    report dict, or None if none has been set yet in this process (or it
    has since been cleared by reset_registry_state()). Deliberately
    returns None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_COMPILER_READINESS_REPORT


def has_current_compiler_readiness_report() -> bool:
    """True once set_current_compiler_readiness_report() has been called
    and before the next reset_registry_state() call."""
    return _CURRENT_COMPILER_READINESS_REPORT is not None


# --------------------------------------------------------------------------
# Phase B5.3: current chapter's compiler build summary, set once per
# chapter by pipeline.py after finalize_compiler_build() finishes and
# cleared by reset_registry_state() above, alongside every other
# current-chapter artifact. Exact same idiom as
# _CURRENT_COMPILER_READINESS_REPORT above -- see module docstring's
# PHASE B5.3 ADDITION note.
# --------------------------------------------------------------------------
_CURRENT_COMPILER_BUILD_SUMMARY: Optional[Dict[str, Any]] = None


def set_current_compiler_build_summary(build_summary: Dict[str, Any]) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.finalize.finalize_compiler_build() finishes aggregating this
    chapter's compiler build -- makes the build summary part of the
    compiler state (task's own "store inside Compiler State"
    requirement), reachable by any later in-process phase via
    get_current_compiler_build_summary(), without ever writing it into
    `manager` itself or into Chapter JSON."""
    global _CURRENT_COMPILER_BUILD_SUMMARY
    _CURRENT_COMPILER_BUILD_SUMMARY = build_summary


def get_current_compiler_build_summary() -> Optional[Dict[str, Any]]:
    """Returns the most recently set_current_compiler_build_summary()'d
    dict, or None if none has been set yet in this process (or it has
    since been cleared by reset_registry_state()). Deliberately returns
    None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_COMPILER_BUILD_SUMMARY


def has_current_compiler_build_summary() -> bool:
    """True once set_current_compiler_build_summary() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_COMPILER_BUILD_SUMMARY is not None


# --------------------------------------------------------------------------
# Phase B5.3: current chapter's final compiler status, set once per
# chapter by pipeline.py after finalize_compiler_build() finishes and
# cleared by reset_registry_state() above. Exact same idiom as
# _CURRENT_COMPILER_BUILD_SUMMARY above.
# --------------------------------------------------------------------------
_CURRENT_FINAL_COMPILER_STATUS: Optional[str] = None


def set_current_final_compiler_status(status: str) -> None:
    """Called once per chapter by pipeline.py, right after
    compiler.finalize.finalize_compiler_build() finishes deriving this
    chapter's final compiler status (READY / READY_WITH_WARNINGS /
    FAILED) -- makes it part of the compiler state, reachable by any
    later in-process phase via get_current_final_compiler_status(),
    without ever writing it into `manager` itself or into Chapter JSON."""
    global _CURRENT_FINAL_COMPILER_STATUS
    _CURRENT_FINAL_COMPILER_STATUS = status


def get_current_final_compiler_status() -> Optional[str]:
    """Returns the most recently set_current_final_compiler_status()'d
    status string, or None if none has been set yet in this process (or
    it has since been cleared by reset_registry_state()). Deliberately
    returns None rather than raising, for the same reason
    get_current_registry_manager() does."""
    return _CURRENT_FINAL_COMPILER_STATUS


def has_current_final_compiler_status() -> bool:
    """True once set_current_final_compiler_status() has been called and
    before the next reset_registry_state() call."""
    return _CURRENT_FINAL_COMPILER_STATUS is not None