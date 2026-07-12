"""
compiler_release/ — Phase F5: Compiler Release Finalization.

SCOPE (frozen F5 architecture, nothing more): this package owns exactly
one thing none of F1-F4 own -- aggregating everything Phase F1
(RuntimeStatus), Phase F2 (Build/Build Manifest), Phase F3
(ExecutionReport), and Phase F4 (CacheEntry/CacheValidationReport)
already computed THIS run into one final, persisted verdict: is this
run, as a whole, a usable Compiler Build? Every one of F1-F4's own
package docstrings independently reserves this exact role for Phase F5
("not Compiler Build packaging, manifest generation, or a release
artifact (F5)") -- see runtime/__init__.py, artifact_manager/__init__.py,
build_executor/__init__.py, and cache/__init__.py's own "F5" call-outs.

Phase F5 NEVER recomputes a fingerprint, validation verdict, execution
decision, or cache comparison -- every field in a CompilerReleaseManifest
is read verbatim off an already-computed F1-F4 accessor, except for the
one new thing this package computes: the Final Release Status itself
(see finalize.determine_final_release_status()).

Deliberately distinct from validation/release.py (Phase D3's own,
chapter-scoped "Release Readiness Report"/finalize_release()): D3's own
"WHAT THIS IS NOT" list explicitly disclaims packaging, and its own
docstring scopes it to one chapter's fourteen chapter-level artifacts.
Phase F5 is the same *shape* of aggregation applied one level up -- for
the whole run, not one chapter -- and deliberately avoids reusing D3's
own naming ("Release Readiness Report" / "Release Decision") anywhere
in this package, to keep the two concepts unambiguous (see
CompilerReleaseManifest, never "Release Manifest" alone, and never
"Build Manifest", already Phase F2's own per-run artifact-index term).

  * `exceptions.py` -- this package's own exception hierarchy
    (CompilerReleaseError and its ReleaseManifestError/
    ReleaseFinalizationError subclasses), mirroring cache/exceptions.py's
    shape one layer over.
  * `report.py` -- `CompilerReleaseManifest`: the full Phase F5 artifact,
    purely a data holder (matches every earlier phase's own
    "dataclass + to_dict(), all computation happens in the owning
    module" convention). Status constants reuse compiler/finalize.py's
    own STATUS_READY/STATUS_READY_WITH_WARNINGS/STATUS_FAILED string
    values verbatim -- not new synonymous strings.
  * `finalize.py` -- determine_final_release_status() (pure function),
    generate_compiler_release_manifest() (pure aggregation), and
    finalize_release() (the one orchestration call CompilerRuntime's own
    _record_release() makes).
  * `persistence.py` -- persist_release_manifest()/load_release_manifest()/
    release_manifest_exists(), reusing the exact same OneDriveStorage
    instance and upload_json()/download_json()/exists() surface F2 and
    F4 already use -- no new serialization format, no new storage
    client, no database. New sibling storage root, deliberately NOT
    nested inside _runtime_builds/ or _runtime_cache/:
    `_runtime_release/<build_id>/release_manifest.json`.
  * `discovery.py` -- list_release_manifests()/release_history(): release
    discovery / release history, over the same storage, via
    list_directory() (no new listing mechanism), mirroring
    cache/index.py's own list_cache_entries()/cache_history() one
    package over.
  * `state.py` -- set/get/has/reset_current_release_manifest_state(): one
    module-level slot (a CompilerReleaseManifest is Phase F5's only
    artifact, unlike Phase F4's own CacheEntry/CacheValidationReport
    pair), run-scoped, the same idiom every other phase's own state.py
    in this codebase already uses.

WHAT THIS IS NOT (see the frozen F5 architecture's own "Phase F5 does
NOT" list): not a new fingerprint, validation verdict, execution
decision, or cache comparison of its own; not gating, skipping, or
influencing anything F3's ExecutionPlan or F4's CacheValidationReport
already decided (a READY_WITH_WARNINGS/FAILED release status is purely
observational -- see finalize.py's own module docstring); not a new
persistence format, storage client, or database; not a change to any
existing public API's return shape (see runtime/runtime.py's own
release_manifest()/release_history()/release_optimization_context()
additions -- purely additive); not a redesign of a single responsibility
already owned by F1, F2, F3, or F4; and not deployment, CI/CD, video
generation, Master JSON, or anything chapter-scoped (all of that remains
exactly where Stage A-E and Phase 1.5 already put it).
"""
from .exceptions import (
    CompilerReleaseError,
    ReleaseFinalizationError,
    ReleaseManifestError,
)
from .report import (
    RELEASE_MANIFEST_VERSION,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    CompilerReleaseManifest,
)
from .finalize import (
    determine_final_release_status,
    finalize_release,
    generate_compiler_release_manifest,
)

__all__ = [
    "CompilerReleaseError",
    "ReleaseFinalizationError",
    "ReleaseManifestError",
    "RELEASE_MANIFEST_VERSION",
    "STATUS_FAILED",
    "STATUS_READY",
    "STATUS_READY_WITH_WARNINGS",
    "CompilerReleaseManifest",
    "determine_final_release_status",
    "finalize_release",
    "generate_compiler_release_manifest",
]
