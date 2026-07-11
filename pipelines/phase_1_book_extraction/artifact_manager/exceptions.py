"""
artifact_manager/exceptions.py — Phase F2: exception hierarchy for the
Artifact Manager (artifact_manager.build/manifest/persistence/discovery).

Mirrors runtime/exceptions.py's and compiler/exceptions.py's own
convention exactly, one package over: small, specific exception classes
so a caller can catch precisely what it cares about instead of parsing
free-text messages.

These are Phase F2's OWN exceptions -- they describe artifact-manager-
level failures (a Build that fails its own invariants, a manifest that
can't be built deterministically, a persistence/storage failure, an
artifact that can't be found or loaded), not compiler/knowledge-graph/
etc. errors. An error raised by an orchestrated phase (RegistryError,
ChangeDetectionError, ...) is never wrapped or hidden by these classes;
it already propagated through CompilerRuntime.run() (see runtime/
runtime.py) before Phase F2's own integration point in _execute() ever
runs.
"""


class ArtifactManagerError(Exception):
    """Base class for every error raised anywhere in the
    artifact_manager package. Mirrors runtime.exceptions.
    CompilerRuntimeError's role as the one catch-all ancestor for its
    own layer."""


class BuildError(ArtifactManagerError):
    """Raised when a Build object cannot be constructed -- e.g. required
    runtime output is missing or malformed. Never raised for "a chapter
    failed" (that is a normal, already-recorded outcome inside the
    per-book stats a Build simply reports on) -- only for Phase F2's own
    inability to assemble the Build object itself."""


class ManifestError(ArtifactManagerError):
    """Raised when a Build Manifest cannot be generated deterministically
    from an already-constructed Build -- e.g. a required Build field is
    missing so no manifest could possibly reference it."""


class PersistenceError(ArtifactManagerError):
    """Raised when persisting (or loading) a Build/Build Manifest via the
    reused OneDriveStorage instance fails. Never raised for an ordinary
    "not found yet" -- see ArtifactError for that -- only for an actual
    storage-layer failure (wraps whatever storage.exceptions error was
    raised, without hiding it: the original exception is always chained
    via `raise ... from exc`)."""


class ArtifactError(ArtifactManagerError):
    """Raised by discovery/loading when a requested build_id does not
    exist, or an artifact record is present but cannot be parsed back
    into a Build/Build Manifest shape."""

    def __init__(self, build_id: str, detail: str = "not found"):
        super().__init__(
            f"artifact_manager: build {build_id!r} — {detail}"
        )
        self.build_id = build_id
