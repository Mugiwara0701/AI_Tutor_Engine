"""
compiler_release/exceptions.py — Phase F5: exception hierarchy for the
Compiler Release package (compiler_release.finalize/persistence/
discovery/report/state).

Mirrors cache/exceptions.py's own convention exactly, one package over:
small, specific exception classes so a caller can catch precisely what
it cares about instead of parsing free-text messages.

These are Phase F5's OWN exceptions -- they describe release-level
failures (a CompilerReleaseManifest that cannot be generated
deterministically from the F1-F4 artifacts it was given, a manifest
that cannot be persisted/loaded), not runtime/artifact-manager/
build-executor/cache errors. An error raised by an orchestrated phase
is never wrapped or hidden by these classes; it already propagated
through CompilerRuntime.run() before Phase F5's own integration point
in _execute() ever runs (see runtime/runtime.py's own _record_release()
"never raises" contract, mirroring _record_build()'s/_record_execution()'s/
_record_cache()'s own contract one phase over).
"""


class CompilerReleaseError(Exception):
    """Base class for every error raised anywhere in the
    compiler_release package. Mirrors cache.exceptions.CacheError's
    role as the one catch-all ancestor for its own layer."""


class ReleaseManifestError(CompilerReleaseError):
    """Raised only if generate_compiler_release_manifest() is given a
    Build with no build_manifest attached -- the same guard
    cache.snapshot_store.build_cache_entry() already applies for its
    own CacheEntry, one package over. Also raised, chaining the
    original storage.exceptions error via `raise ... from exc`, if
    persist_release_manifest()/load_release_manifest() hit an actual
    storage failure (mirrors cache.snapshot_store's own
    CacheWriteError/CacheReadError contract, collapsed into this one
    class since Phase F5 has exactly one artifact rather than F4.1's
    own read/write pair)."""


class ReleaseFinalizationError(CompilerReleaseError):
    """Raised only if finalize_release() cannot determine any Final
    Release Status at all -- practically unreachable given
    determine_final_release_status()'s own closed fallback (every
    RuntimeStatus value maps to exactly one of READY/
    READY_WITH_WARNINGS/FAILED), kept only for symmetry with every
    other phase's own finalization-error class (see
    incremental_compilation_finalization/exceptions.py's own
    precedent, one phase over)."""
