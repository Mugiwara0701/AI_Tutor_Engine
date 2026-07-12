"""
cache/exceptions.py — Phase F4.1: exception hierarchy for the Cache
package (cache.snapshot_store/index/validation/report/state).

Mirrors artifact_manager/exceptions.py's and build_executor/
exceptions.py's own convention exactly, one package over: small,
specific exception classes so a caller can catch precisely what it
cares about instead of parsing free-text messages.

These are Phase F4.1's OWN exceptions -- they describe cache-level
failures (a fingerprint snapshot that cannot be persisted/loaded, a
CacheValidationReport that cannot be generated deterministically from
the inputs it was given), not compiler/knowledge-graph/artifact-
manager/build-executor errors. An error raised by an orchestrated
phase (RegistryError, ChangeDetectionError, BuildError,
ExecutionPlanError, ...) is never wrapped or hidden by these classes;
it already propagated through CompilerRuntime.run() before Phase
F4.1's own integration point in _execute() ever runs (see
runtime/runtime.py's own _record_cache() "never raises" contract,
mirroring _record_build()'s/_record_execution()'s own contract one
phase over).
"""


class CacheError(Exception):
    """Base class for every error raised anywhere in the cache
    package. Mirrors artifact_manager.exceptions.ArtifactManagerError's
    and build_executor.exceptions.BuildExecutorError's role as the one
    catch-all ancestor for its own layer."""


class CacheWriteError(CacheError):
    """Raised when a fingerprint snapshot cannot be persisted via the
    reused OneDriveStorage instance -- e.g. the underlying storage call
    fails, or the snapshot to persist is missing its required
    `build_id`. Wraps whatever storage.exceptions error was raised,
    without hiding it: the original exception is always chained via
    `raise ... from exc`."""


class CacheReadError(CacheError):
    """Raised when a previously persisted fingerprint snapshot cannot
    be loaded -- either because no such build_id was ever cached
    (`build_id` is attached to this exception so a caller can log or
    branch on it) or because the storage read itself fails for some
    other reason."""

    def __init__(self, build_id: str, detail: str = "not found"):
        super().__init__(f"cache: fingerprint snapshot for build {build_id!r} — {detail}")
        self.build_id = build_id


class CacheValidationError(CacheError):
    """Raised when a CacheValidationReport cannot be generated
    deterministically from the ExecutionPlan/fingerprint snapshots it
    was given -- e.g. a required field is missing so no report could
    possibly reference it."""


class CacheSnapshotInvalidError(CacheError):
    """Phase F4.2: raised when a previously persisted CacheEntry was
    read successfully (no CacheReadError) but its own SHAPE cannot be
    trusted as a valid F4.1 CacheEntry (build_cache_entry()'s own
    shape) -- e.g. not a dict, missing `build_id`/`fingerprint_snapshot`,
    `fingerprint_snapshot` not itself a dict, or a `build_id` field that
    does not match the build_id the record was loaded for (a storage-
    layer mixup, not a fingerprint concern). This is distinct from
    CacheReadError (the record could not be *read* at all) -- this is
    "the record was read, but its own contents are not a CacheEntry a
    later run can safely consume." `build_id` is attached so a caller
    can log or branch on it, same convention CacheReadError already
    uses."""

    def __init__(self, build_id: str, detail: str):
        super().__init__(
            f"cache: fingerprint snapshot for build {build_id!r} is not a "
            f"valid CacheEntry -- {detail}"
        )
        self.build_id = build_id