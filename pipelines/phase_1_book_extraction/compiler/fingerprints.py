"""
compiler/fingerprints.py — Phase B5.2: Compiler Fingerprints & Readiness.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, Phase B1c, Phase B2, Phase B3, Phase B4, and Phase
B5.1 are frozen -- this module does not redesign RegistryManager
(compiler/registry_manager.py), CanonicalRegistry (compiler/registry.py),
compiler/state.py's existing _CURRENT_* lifecycle, compiler/enrichment.py,
compiler/normalization.py, compiler/references.py, compiler/
relationships.py, compiler/validation.py, or compiler/build.py. It also
does not touch json_writer.py / schemas/chapter_schema.py / ChapterJSON.
It ONLY adds a seventh, read-only compiler pass that DERIVES deterministic
fingerprints and a readiness verdict from what Phases A-B5.1 already
computed -- it never generates, repairs, or mutates a single field
anywhere in the compiler IR, and it never inserts into, updates, or
removes from any registry.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Compiler Build Summary, not a Final Compiler Status Report, not a
Knowledge Graph (or any graph construction/traversal/dependency/learning
graph), not Incremental Compilation, not a Compiler Cache, and not
Automatic Repair. The readiness report below is READ-ONLY: it inspects
and reports, it never fixes anything it finds missing or failing.

REUSE, DON'T RECOMPUTE (mirrors every earlier compiler pass's own rule):
registry fingerprints are derived from each registry's own
`CanonicalRegistry.serialize()` output (already deterministic,
insertion-ordered -- see compiler/registry.py's own module docstring),
never from a hand-rolled re-walk of registry internals. The compiler
fingerprint is derived from the registry fingerprints plus the SAME
`manifest`/`statistics` dicts compiler.build.generate_compiler_manifest()/
generate_compiler_statistics() already produced this chapter -- nothing
here re-derives a manifest or statistics field a second time. The
readiness report's checks read `manager.names()`/`manager.has()`
(RegistryManager's own cheap accessors), the validation report's own
`status` field, and the fingerprints/manifest/statistics already computed
above -- nothing here re-validates the compiler IR itself (that is
Phase B4's job, not this module's).

DETERMINISM GUARANTEE: `generate_registry_fingerprints()` and
`generate_compiler_fingerprint()` are pure functions of already-computed,
deterministic compiler state. Same compiler IR (same registries, same
manifest/statistics content, modulo volatile fields -- see VOLATILE FIELD
FILTERING below) -> byte-identical canonical JSON -> the same SHA-256
digest, on this run and every future one, on any machine. Different
compiler IR -> a different canonical JSON payload (with overwhelming
probability, i.e. barring a SHA-256 collision) -> a different digest.
Nothing here reads a timestamp, a memory address, an object id(), or
Python's hash-randomized dict/set iteration order into a fingerprint --
every registry/manifest/statistics dict involved already iterates in
deterministic (insertion or explicit sort) order per its own owning
module's docstring, and `_canonical_json()` below additionally
`sort_keys=True`s every dict before hashing, so even a hypothetical
future producer that emits keys in a different order still fingerprints
identically.

VOLATILE FIELD FILTERING: every timestamp-shaped field any earlier phase
already stamps onto compiler IR -- `provenance.timestamp` and
`creation_metadata.created_at` (modules/canonical.py), `registry_metadata.
enriched_at` (compiler/enrichment.py), `normalization.normalized_at`
(compiler/normalization.py), `reference_resolution.resolved_at`
(compiler/references.py), `relationship_resolution.resolved_at`
(compiler/relationships.py), and every artifact's own top-level
`generated_at` (compiler/validation.py's ValidationReport, compiler/
build.py's CompilerManifest/CompilerStatistics) -- is excluded before
hashing, by key name, at any nesting depth, via `_strip_volatile()`
below. `approx_memory_bytes` (compiler/registry.py's RegistryStatistics)
is excluded for the same reason the task spec calls out "memory
addresses": it is a `sys.getsizeof()`-derived diagnostic, not a fact
about the compiler IR's actual content, and has no business affecting
whether two IRs with identical content fingerprint the same. Excluding a
field by name (rather than, say, a fixed set of dict paths) is
deliberate: it means a future phase that stamps a new
`whatever_at`/`whatever_timestamp`-shaped field onto compiler IR is
automatically excluded too, without this module needing to be told about
every new volatile field some other, later phase introduces -- see
VOLATILE_KEYS below for the exact, closed set of key names this phase
already knows about today.

NEVER DEPENDS ON: timestamps, memory addresses, object identities,
dictionary ordering, or random values -- see DETERMINISM GUARANTEE and
VOLATILE FIELD FILTERING above for exactly how each of these is avoided.

TASK 1 -- Registry Fingerprints: `generate_registry_fingerprints(manager)`
returns one SHA-256 hex digest per registry `manager` owns, keyed by
registry name (same keys as `manager.names()`), each digest derived from
that registry's own `serialize()` output with volatile fields stripped.

TASK 2 -- Compiler Fingerprint: `generate_compiler_fingerprint(...)`
folds every registry fingerprint (Task 1) together with the B5.1
manifest and statistics (volatile fields stripped) into one SHA-256 hex
digest representing the complete compiler IR for this chapter.

TASK 3 -- Compiler Readiness Report: `generate_compiler_readiness_report(
...)` runs the task's own seven read-only checks (required registries
exist, validation completed successfully, manifest exists, statistics
exist, registry fingerprints generated, compiler fingerprint generated,
relationships registry available) and returns a structured, read-only
verdict. It never repairs anything it finds missing -- a failed check is
reported, not fixed.

PIPELINE INTEGRATION (Task 5): `generate_compiler_fingerprints()` is the
one pipeline.py integration point (mirrors generate_compiler_manifest()'s
own shape). It must run AFTER compiler.build.generate_compiler_manifest()/
generate_compiler_statistics() (so there is a manifest/statistics to fold
into the compiler fingerprint) and BEFORE
compiler_state.set_current_registry_manager() (so it describes
`registry_manager` exactly as it is about to become "current") -- see
pipeline.py's own integration comment at the call site. Its three
results (registry fingerprints, compiler fingerprint, readiness report)
are handed to compiler_state.set_current_registry_fingerprints() /
set_current_compiler_fingerprint() / set_current_compiler_readiness_
report() immediately after (this phase's own additions to compiler/
state.py -- see that module's docstring), making them "part of Compiler
State" per the task spec, WITHOUT writing any of them into ChapterJSON,
onto `manager` itself, or into the compiler IR.

BACKWARD COMPATIBILITY: every field this module reads (from `manager`,
from `manifest`, from `statistics`, from `validation_report`) is only
ever read, never changed. No existing registry, field, relationship,
manifest, statistics, validation report, or Chapter JSON output changes
as a result of this module existing. The only new compiler artifacts are
the registry fingerprints dict, the compiler fingerprint string, and the
readiness report dict (plus the six small, additive get/set/has
functions in compiler/state.py that hold them).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .registry_manager import RegistryManager
from .registries import REGISTRY_NAMES
from .relationships import RELATIONSHIP_REGISTRY_NAME

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of every earlier phase's
# own *_VERSION constant). Bump only if the fingerprint ALGORITHM itself
# changes (e.g. a different hash function, a different canonicalization
# strategy, or a change to VOLATILE_KEYS) in a way that would make an old
# fingerprint and a new fingerprint of the same underlying IR legitimately
# differ -- a consumer diffing fingerprints across a FINGERPRINT_VERSION
# bump should expect a change even for unchanged compiler IR.
FINGERPRINT_VERSION = "1.0.0"

# Every key name this phase excludes from fingerprinting, at any nesting
# depth, in any registry item / manifest / statistics dict -- see module
# docstring's VOLATILE FIELD FILTERING section for exactly which
# earlier-phase field each entry corresponds to and why.
VOLATILE_KEYS = frozenset({
    "generated_at",             # ValidationReport / CompilerManifest / CompilerStatistics
    "enriched_at",               # compiler/enrichment.py: registry_metadata.enriched_at
    "normalized_at",             # compiler/normalization.py: normalization.normalized_at
    "resolved_at",                # compiler/references.py & compiler/relationships.py
    "created_at",                 # modules/canonical.py: creation_metadata.created_at
    "timestamp",                   # modules/canonical.py: provenance.timestamp
    "approx_memory_bytes",         # compiler/registry.py: RegistryStatistics (memory-derived)
})


# --------------------------------------------------------------------------
# Canonicalization helpers
# --------------------------------------------------------------------------

def _strip_volatile(value: Any) -> Any:
    """Recursively returns a copy of `value` with every VOLATILE_KEYS
    entry removed from every dict at every nesting depth. Lists are
    walked (not sorted -- every list this module ever fingerprints is
    already produced in a deterministic, insertion/explicit-sort order
    by its owning phase; re-sorting here would be new, unrequested
    normalization behavior, not fingerprinting). Scalars pass through
    unchanged. Never mutates `value` itself."""
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    """Deterministic JSON text for `value`: volatile fields stripped
    (see _strip_volatile), keys sorted (so hash-randomized dict
    iteration order can never affect the result), and a compact,
    fixed separator style (so incidental whitespace differences never
    affect the result either). `default=str` is a defensive fallback
    only -- every value this module ever fingerprints is already plain
    JSON-compatible data (CanonicalRegistry.serialize() / the B5.1
    manifest+statistics dicts), never a live object."""
    return json.dumps(
        _strip_volatile(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_hexdigest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Task 1: Registry Fingerprints
# --------------------------------------------------------------------------

def generate_registry_fingerprints(manager: RegistryManager) -> Dict[str, str]:
    """Phase B5.2 Task 1. One SHA-256 hex digest per registry `manager`
    owns, keyed by registry name (same names as `manager.names()`, same
    deterministic registration order).

    Read-only over `manager`: no registry is inserted into, updated, or
    removed from. Each registry's digest is computed from its own
    `CanonicalRegistry.serialize()` output (already deterministic,
    insertion-ordered -- see compiler/registry.py) with every
    VOLATILE_KEYS field stripped first -- see module docstring's
    DETERMINISM GUARANTEE / VOLATILE FIELD FILTERING sections. Never
    rescans registry internals directly (`_items`/`_urn_index`/
    `_name_index`); `serialize()` is the one existing, public,
    already-tested source of truth for "this registry's deterministic
    contents", reused unchanged.

    Same registry contents (modulo volatile fields) -> the same digest,
    every run. A registry with zero items still gets a digest (of its
    empty `{"registry": name, "version": 1, "items": []}` envelope) --
    "empty" is itself a deterministic, fingerprint-worthy state, not a
    reason to skip a registry.
    """
    fingerprints: Dict[str, str] = {}
    for name in manager.names():
        registry = manager.get(name)
        payload = registry.serialize()
        fingerprints[name] = _sha256_hexdigest(_canonical_json(payload))
    return fingerprints


# --------------------------------------------------------------------------
# Task 2: Compiler Fingerprint
# --------------------------------------------------------------------------

def generate_compiler_fingerprint(
    registry_fingerprints: Dict[str, str],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
) -> str:
    """Phase B5.2 Task 2. One SHA-256 hex digest representing the
    complete compiler IR, derived from (task's own three-item list):

      * `registry_fingerprints` (Task 1's own output -- every per-
        registry digest, sorted by name below so caller-supplied dict
        ordering can never affect the result)
      * `manifest` (compiler.build.generate_compiler_manifest()'s
        output this chapter, volatile fields stripped)
      * `statistics` (compiler.build.generate_compiler_statistics()'s
        output this chapter, volatile fields stripped)

    Read-only over all three arguments -- nothing here mutates a
    fingerprint dict, a manifest, or a statistics dict, and nothing here
    re-derives manifest/statistics fields a second time (Task 2's own
    "reuse, don't recompute" rule -- see module docstring).

    Same compiler IR -> same registry fingerprints + same manifest/
    statistics content (modulo volatile fields) -> the same digest, every
    run. Different compiler IR -> a different digest (barring a SHA-256
    collision).
    """
    payload = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "registry_fingerprints": dict(sorted((registry_fingerprints or {}).items())),
        "manifest": manifest or {},
        "statistics": statistics or {},
    }
    return _sha256_hexdigest(_canonical_json(payload))


# --------------------------------------------------------------------------
# Task 3: Compiler Readiness Report
# --------------------------------------------------------------------------

# The task's own "required registries" list: every educational-object
# registry create_registry_manager() always registers (compiler/
# registries.py's REGISTRY_NAMES), plus the relationships registry
# (compiler/relationships.py's RELATIONSHIP_REGISTRY_NAME), which is
# created on demand by resolve_relationships() rather than by
# create_registry_manager() itself but is required to exist by the time
# this phase runs (pipeline.py always runs resolve_relationships() before
# this pass -- see PIPELINE INTEGRATION above).
REQUIRED_REGISTRY_NAMES: List[str] = list(REGISTRY_NAMES) + [RELATIONSHIP_REGISTRY_NAME]


@dataclass
class CompilerReadinessReport:
    """The full Phase B5.2 readiness artifact -- see module docstring's
    TASK 3 section. Purely a data holder; all the actual checking
    happens in generate_compiler_readiness_report() below, which reads
    already-computed compiler state and folds it into one of these. This
    report is READ-ONLY reporting -- it never repairs anything a failed
    check finds missing."""

    generated_at: str
    ready: bool
    compiler_status: str
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    readiness_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compiler_readiness_report(
    manager: RegistryManager,
    validation_report: Optional[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    registry_fingerprints: Optional[Dict[str, str]],
    compiler_fingerprint: Optional[str],
) -> Dict[str, Any]:
    """Phase B5.2 Task 3. Runs the task's own seven read-only checks and
    returns a structured, deterministic verdict as a plain dict
    (report.to_dict()), matching every earlier phase's own "plain,
    storable dict" convention.

    Read-only over every argument: no registry is inserted into,
    updated, or removed from; nothing is repaired, filled in, or
    regenerated here -- a failed check is reported as failed, never
    silently fixed (task's own "This report must be read-only. Never
    repair anything automatically.").
    """
    passed_checks: List[str] = []
    failed_checks: List[str] = []
    warnings: List[str] = []

    # -- 1. required registries exist ------------------------------------
    missing_registries = [n for n in REQUIRED_REGISTRY_NAMES if not manager.has(n)]
    if not missing_registries:
        passed_checks.append("required_registries_exist")
    else:
        failed_checks.append("required_registries_exist")
        warnings.append(
            "missing required registries: " + ", ".join(missing_registries)
        )

    # -- 2. validation completed successfully -----------------------------
    validation_status = (validation_report or {}).get("status")
    if validation_report is not None and validation_status == "pass":
        passed_checks.append("validation_completed")
    else:
        failed_checks.append("validation_completed")
        if validation_report is None:
            warnings.append("no validation report available")
        else:
            error_count = len(validation_report.get("errors") or [])
            warnings.append(
                f"validation reported status={validation_status!r} "
                f"with {error_count} error(s)"
            )

    # -- 3. manifest exists -------------------------------------------------
    if manifest:
        passed_checks.append("manifest_exists")
    else:
        failed_checks.append("manifest_exists")

    # -- 4. statistics exist -------------------------------------------------
    if statistics:
        passed_checks.append("statistics_exist")
    else:
        failed_checks.append("statistics_exist")

    # -- 5. registry fingerprints generated ----------------------------------
    expected_registry_names = set(manager.names())
    have_all_registry_fingerprints = bool(registry_fingerprints) and expected_registry_names.issubset(
        set(registry_fingerprints)
    )
    if have_all_registry_fingerprints:
        passed_checks.append("registry_fingerprints_generated")
    else:
        failed_checks.append("registry_fingerprints_generated")

    # -- 6. compiler fingerprint generated -----------------------------------
    if compiler_fingerprint:
        passed_checks.append("compiler_fingerprint_generated")
    else:
        failed_checks.append("compiler_fingerprint_generated")

    # -- 7. relationships registry available ---------------------------------
    if manager.has(RELATIONSHIP_REGISTRY_NAME):
        passed_checks.append("relationships_registry_available")
    else:
        failed_checks.append("relationships_registry_available")

    # Surface validation warnings (not just errors) as a non-blocking
    # signal on the readiness report -- a compiler build can be "ready"
    # (zero validation errors) while still carrying warnings worth a
    # human's attention. Never affects `ready` below.
    if validation_report is not None:
        validation_warning_count = len(validation_report.get("warnings") or [])
        if validation_warning_count:
            warnings.append(
                f"validation report carries {validation_warning_count} "
                "warning(s)"
            )

    ready = not failed_checks
    # Same carry-forward pattern compiler/build.py's own `compiler_status`
    # field already documents: the only status judgment this compiler
    # currently computes anywhere is Phase B4's validation verdict, so
    # `compiler_status` here is that same verdict, exposed under this
    # report's own field name -- not a second, independently-computed
    # judgment.
    compiler_status = validation_status or "unknown"

    readiness_summary = {
        "total_checks": len(passed_checks) + len(failed_checks),
        "passed_count": len(passed_checks),
        "failed_count": len(failed_checks),
        "warning_count": len(warnings),
    }

    report = CompilerReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        ready=ready,
        compiler_status=compiler_status,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        warnings=warnings,
        readiness_summary=readiness_summary,
    )
    return report.to_dict()


# --------------------------------------------------------------------------
# Task 5: Pipeline Integration -- the one pass pipeline.py calls
# --------------------------------------------------------------------------

def generate_compiler_fingerprints(
    manager: RegistryManager,
    *,
    manifest: Optional[Dict[str, Any]],
    statistics: Optional[Dict[str, Any]],
    validation_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Phase B5.2's single pipeline.py integration point (mirrors
    compiler.build.generate_compiler_manifest()'s own shape). Must run
    AFTER compiler.build.generate_compiler_manifest()/
    generate_compiler_statistics() (so `manifest`/`statistics` are
    available to fold into the compiler fingerprint) and BEFORE
    compiler_state.set_current_registry_manager() -- see module
    docstring's PIPELINE INTEGRATION section and pipeline.py's own
    comment at the call site.

    Runs Tasks 1-3 in the only order that makes sense (fingerprints
    before the readiness report that checks whether they were
    generated) and returns all three results together as one plain dict,
    ready to be handed to compiler_state.set_current_registry_
    fingerprints() / set_current_compiler_fingerprint() /
    set_current_compiler_readiness_report() (task's own "store inside
    Compiler State" requirement).

    Read-only over every argument, and never touches the compiler IR
    itself -- see module docstring's opening SCOPE paragraph.
    """
    registry_fingerprints = generate_registry_fingerprints(manager)
    compiler_fingerprint = generate_compiler_fingerprint(
        registry_fingerprints, manifest, statistics,
    )
    readiness_report = generate_compiler_readiness_report(
        manager,
        validation_report,
        manifest,
        statistics,
        registry_fingerprints,
        compiler_fingerprint,
    )
    return {
        "registry_fingerprints": registry_fingerprints,
        "compiler_fingerprint": compiler_fingerprint,
        "readiness_report": readiness_report,
    }
