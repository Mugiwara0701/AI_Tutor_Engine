"""
artifact_manager/manifest.py — Phase F2: deterministic Build Manifest
generation.

THE BUILD MANIFEST IS THE SOLE AUTHORITATIVE ARTIFACT INDEX FOR A BUILD.
Build (build.py) still carries its own eight `*_reference` fields as
plain dataclass attributes -- kept exactly as originally shipped, for
backward compatibility with any existing caller reading
`build.compiler_ir_reference` etc. directly -- but this module is now
where those same values are gathered a second time, verbatim (never
re-derived), into one clearly-named, versioned, fingerprinted,
persisted section: `chapter_state_references` below, sitting alongside
this manifest's own pre-existing `artifact_locations` (the
comprehensive, real, every-chapter-this-run-wrote path index). Together
those two top-level manifest fields ARE this build's complete artifact
index; `build.build_manifest` (once `Build.with_manifest()` has run) is
the one place any NEW caller should read either from -- see
`Build.artifact_index` (build.py) for the accessor that makes this the
path of least resistance. The individual `Build.*_reference` fields
remain a read-only, backward-compatible mirror of exactly
`chapter_state_references` below -- never an independent second source
of truth, since both are populated from the same single
build_reference_snapshot() read (build.py) and never diverge.

REUSE, DON'T RECOMPUTE (same rule build_metadata/build.py's own module
docstring already states for Phase E1, one layer up): every field below
is read from an already-constructed Build (build.py) -- this module
performs no new fingerprinting, no new validation, and no new artifact
computation of its own. The one new thing it computes is
`manifest_fingerprint` itself, a plain deterministic hash of the
manifest's own other fields (so two manifests generated from identical
Build content always hash identically) -- not a fingerprint of any
compiler/knowledge-graph content, which Phase B/C already fingerprinted
via compiler.fingerprints/knowledge_graph.fingerprints (those existing
fingerprints, where a Build carries them, are surfaced verbatim under
`fingerprints` below, never recomputed).

ARTIFACT_LOCATIONS, INCLUDING THIS BUILD'S OWN RECORD PATHS, ARE ATTACHED
IN ONE PASS: `attach_artifact_locations()` below fills in
`build_record_path`/`manifest_record_path` alongside `chapter_json_paths`/
`book_manifest_paths` in the SAME call, before `persistence.persist_build()`
ever runs -- `build_record_path()`/`manifest_record_path()` (persistence.py)
are pure functions of `build.build_id`, so both are known up front and this
never requires a second attach-then-persist-again pass. This is what
guarantees the manifest object actually written to storage and the
manifest attached to the in-memory `Build` are the same dict, byte for
byte -- see runtime/runtime.py's `_record_build()` for the one call site
that does this.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .build import BUILD_VERSION, Build
from .exceptions import ManifestError

# This module's own version marker -- bumped only if the SHAPE this
# module produces changes in a way a consumer should be able to detect.
MANIFEST_SCHEMA_VERSION = "F2.1"


def _artifact_fingerprint(reference: Optional[Dict[str, Any]], *keys: str) -> Optional[str]:
    """Reads an already-computed fingerprint straight out of one of
    Build's `*_reference` dicts (see build.py's own module docstring for
    that shape), trying each of `keys` in turn against the wrapped
    artifact. Returns None if the reference itself is absent or none of
    `keys` is present -- never derives a fingerprint of its own."""
    if not reference:
        return None
    artifact = reference.get("artifact") or {}
    for key in keys:
        value = artifact.get(key)
        if value is not None:
            return value
    return None


def _collect_fingerprints(build: Build) -> Dict[str, Optional[str]]:
    """Surfaces every existing fingerprint a Build's own references
    already carry, verbatim. Compiler/knowledge-graph fingerprints live
    nested inside build_metadata_reference's own CompilerMetadata/
    GraphMetadata blocks (see build_metadata/build.py) when a
    BuildMetadata snapshot is present; this falls back to reading them
    directly off compiler_ir_reference/knowledge_graph_reference when
    build_metadata_reference itself is absent (e.g. an incremental-only
    run that never reached Phase E1 for its last chapter)."""
    bm_artifact = (build.build_metadata_reference or {}).get("artifact") or {}
    compiler_metadata = bm_artifact.get("compiler_metadata") or {}
    graph_metadata = bm_artifact.get("graph_metadata") or {}
    configuration_metadata = bm_artifact.get("configuration_metadata") or {}

    compiler_fingerprint = compiler_metadata.get("compiler_fingerprint") or _artifact_fingerprint(
        build.compiler_ir_reference, "compiler_fingerprint"
    )
    graph_fingerprint = graph_metadata.get("graph_fingerprint") or _artifact_fingerprint(
        build.knowledge_graph_reference, "graph_fingerprint"
    )
    configuration_fingerprint = configuration_metadata.get("configuration_fingerprint")

    return {
        "compiler_fingerprint": compiler_fingerprint,
        "graph_fingerprint": graph_fingerprint,
        "configuration_fingerprint": configuration_fingerprint,
    }


def _collect_versions(build: Build) -> Dict[str, Optional[str]]:
    """Same "surface, don't recompute" treatment as _collect_fingerprints,
    for version markers -- reads compiler_version/schema_version off
    whichever reference already carries them."""
    bm_artifact = (build.build_metadata_reference or {}).get("artifact") or {}
    version_metadata = bm_artifact.get("version_metadata") or {}

    compiler_version = version_metadata.get("compiler_version") or _artifact_fingerprint(
        build.compiler_ir_reference, "compiler_version"
    )
    schema_version = version_metadata.get("schema_version")
    return {"compiler_version": compiler_version, "schema_version": schema_version}


def _collect_warnings_and_errors(build: Build) -> (List[str], List[str]):
    """Errors/warnings a manifest reports are exactly the ones this run
    already surfaced -- book-level errors from execution_summary
    (books_with_errors/error) and, where present, the last processed
    chapter's own already-computed release/validation warnings (read
    off build_metadata_reference, never re-derived)."""
    warnings: List[str] = []
    errors: List[str] = []

    summary = build.execution_summary or {}
    if summary.get("error"):
        errors.append(str(summary["error"]))
    for book_name in summary.get("books_with_errors") or []:
        errors.append(f"book failed entirely: {book_name}")
    if summary.get("chapters_failed"):
        warnings.append(
            f"{summary['chapters_failed']} chapter(s) failed extraction this run "
            "(see per-book stats for detail; a chapter failure does not fail "
            "the whole run)."
        )

    bm_artifact = (build.build_metadata_reference or {}).get("artifact") or {}
    if bm_artifact.get("final_compiler_status") not in (None, "READY"):
        warnings.append(
            f"last processed chapter's compiler status was "
            f"{bm_artifact.get('final_compiler_status')!r}, not READY."
        )
    if bm_artifact.get("final_graph_status") not in (None, "READY"):
        warnings.append(
            f"last processed chapter's knowledge-graph status was "
            f"{bm_artifact.get('final_graph_status')!r}, not READY."
        )

    return warnings, errors


def _collect_chapter_state_references(build: Build) -> Dict[str, Optional[Dict[str, Any]]]:
    """Gathers Build's own eight `*_reference` fields, verbatim, into
    one manifest section. This is a plain re-packaging, not a second
    read of Phase A-E1 state -- build_reference_snapshot() (build.py)
    already did the one and only read of compiler.state/knowledge_graph.
    state/etc.; both this dict and Build's own attributes come from
    that exact same call, so they can never disagree with each other."""
    return {
        "compiler_ir_reference": build.compiler_ir_reference,
        "knowledge_graph_reference": build.knowledge_graph_reference,
        "dependency_graph_reference": build.dependency_graph_reference,
        "build_metadata_reference": build.build_metadata_reference,
        "change_detection_reference": build.change_detection_reference,
        "incremental_plan_reference": build.incremental_plan_reference,
        "incremental_validation_reference": build.incremental_validation_reference,
        "incremental_finalization_reference": build.incremental_finalization_reference,
    }


def _manifest_fingerprint(payload: Dict[str, Any]) -> str:
    """Deterministic SHA-256 over the manifest's own other fields (JSON-
    canonicalized: sorted keys, no whitespace) -- so re-generating a
    manifest from identical Build content always yields the same
    fingerprint, mirroring compiler.fingerprints'/knowledge_graph.
    fingerprints' own "canonical JSON -> sha256" recipe one layer up,
    without importing either module (this manifest's own fingerprint is
    of the MANIFEST, not of any compiler/graph content -- those are
    surfaced, not recomputed, under `fingerprints` instead)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_build_manifest(build: Build) -> Dict[str, Any]:
    """Deterministically generates this Build's Build Manifest -- the
    sole authoritative artifact index for this build (see module
    docstring): `artifact_locations` (the comprehensive, real,
    every-chapter path index) plus `chapter_state_references` (this
    build's own eight reference fields, mirrored verbatim) together
    describe everything Phase F2 knows this build produced or touched.
    Pure function of `build`'s own already-set fields -- calling this
    twice on the same Build (before build_manifest is attached, i.e.
    before Build.with_manifest()) always returns byte-identical output.

    Raises ManifestError if `build` is missing execution_summary (the
    one field every other manifest field is ultimately derived from --
    create_build() always sets it, so this only fires for a
    hand-constructed Build missing it)."""
    if not build.execution_summary:
        raise ManifestError(
            "generate_build_manifest(): build.execution_summary is required "
            "to generate a Build Manifest (create_build() always sets it)."
        )

    fingerprints = _collect_fingerprints(build)
    versions = _collect_versions(build)
    warnings, errors = _collect_warnings_and_errors(build)
    chapter_state_references = _collect_chapter_state_references(build)

    summary = build.execution_summary
    build_status = summary.get("status", "UNKNOWN")

    artifact_locations: Dict[str, Any] = {
        # Populated by persistence.py once this manifest's own Build has
        # actually been written -- left empty here since a manifest is
        # generated BEFORE persistence happens (persist_build() needs a
        # manifest to persist in the first place). See persistence.py's
        # own module docstring.
        "chapter_json_paths": [],
        "book_manifest_paths": [],
        "build_record_path": None,
        "manifest_record_path": None,
    }

    payload = {
        "build_id": build.build_id,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "compiler_version": versions["compiler_version"],
        "runtime_version": BUILD_VERSION,
        "build_status": build_status,
        "fingerprints": fingerprints,
        "artifact_locations": artifact_locations,
        # This build's own eight reference fields, mirrored verbatim --
        # see module docstring: together with `artifact_locations` above,
        # this makes the manifest (not Build's own attributes) the one
        # place to read this build's complete artifact index from.
        "chapter_state_references": chapter_state_references,
        "warnings": warnings,
        "errors": errors,
        "execution_summary": summary,
        # Deterministic, not wall-clock: derived from this Build's own
        # already-fixed finished_at (create_build() sets it once, from
        # real wall-clock time, when the Build itself was constructed) --
        # so generate_build_manifest() stays a pure function of `build`,
        # never re-stamping "now" a second time on every regeneration.
        "generated_at": summary.get("finished_at"),
    }
    payload["manifest_fingerprint"] = _manifest_fingerprint(payload)
    return payload


def attach_artifact_locations(
    manifest: Dict[str, Any],
    *,
    chapter_json_paths: List[str],
    book_manifest_paths: List[str],
    build_record_path: Optional[str] = None,
    manifest_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns a NEW manifest dict with `artifact_locations` filled in
    from this run's own already-written chapter JSON / book manifest
    paths (book_orchestrator.run()'s own additive `written_paths`/
    `book_manifest_path` per-book stats keys -- see pipeline.py) plus, if
    given, the path(s) this Build/manifest were themselves persisted to
    (persistence.py calls this a second time, after persist_build() has
    a real path, so the manifest that ends up stored on disk records its
    own location too). Never mutates `manifest` in place -- manifests are
    treated as immutable records once generated, same convention as
    Build itself."""
    updated = dict(manifest)
    updated["artifact_locations"] = {
        "chapter_json_paths": list(chapter_json_paths),
        "book_manifest_paths": list(book_manifest_paths),
        "build_record_path": build_record_path,
        "manifest_record_path": manifest_record_path,
    }
    # Re-fingerprint: artifact_locations is part of the manifest's own
    # content, so filling it in changes what manifest_fingerprint must
    # cover -- same determinism contract as the initial generation above.
    fingerprint_input = {k: v for k, v in updated.items() if k != "manifest_fingerprint"}
    updated["manifest_fingerprint"] = _manifest_fingerprint(fingerprint_input)
    return updated