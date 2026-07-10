"""
compiler/build.py — Phase B5.1: Compiler Manifest & Statistics.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, Phase B1c, Phase B2, Phase B3, and Phase B4 are
frozen -- this module does not redesign RegistryManager (compiler/
registry_manager.py), compiler/state.py's existing
_CURRENT_REGISTRY_MANAGER/_CURRENT_VALIDATION_REPORT lifecycle,
compiler/enrichment.py, compiler/normalization.py, compiler/references.py,
compiler/relationships.py, or compiler/validation.py. It also does not
touch json_writer.py / schemas/chapter_schema.py / ChapterJSON. It ONLY
adds a sixth, read-only compiler pass that DESCRIBES the compiler build
that Phases A-B4 already produced -- a manifest and a statistics report --
by reading fields those earlier, frozen phases already computed. It never
generates, repairs, or mutates a single field anywhere in the compiler IR.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Registry/Compiler Fingerprints, not Compiler Readiness, not a Build
Summary, not Incremental Compilation, not a Compiler Cache, and not a
Knowledge Graph. It does not decide whether the compiler build is
"ready" for anything later -- it only reports what already happened.
Every fingerprint-shaped or readiness-shaped judgment is deliberately
left out; see COMPILER_STATUS FIELDS below for exactly what
`compiler_status`/`build_status` do (and do not) mean here.

REUSE, DON'T RECOMPUTE (mirrors every earlier compiler pass's own rule):
this module accepts the SAME `validation_report` dict
compiler.validation.validate_compiler_state() already produced this
chapter (report["statistics"], report["registry_summary"],
report["reference_summary"], report["relationship_summary"]) and reads
its already-computed counts/summaries directly, rather than re-scanning
every registry a second time. The one piece of data validate_compiler_
state() does not already expose in one shot -- per-registry object counts
-- is read from RegistryManager.statistics() (compiler/registry_manager.py,
itself backed by CanonicalRegistry's own running counters, not a rescan
of every item). Nothing in this module iterates registry.values() /
registry.ids() itself.

MANIFEST vs STATISTICS: `generate_compiler_manifest()` (Task 1) produces
a small, fixed-shape identity/versioning record for this compiler build
(compiler_version, schema_version, build_version, chapter_identifier,
registry_versions, registry_count, object_count, relationship_count,
validation_status, compiler_status, build_status -- the task's own
required-fields list). `generate_compiler_statistics()` (Task 2) produces
the larger, descriptive breakdown (objects per registry, registry sizes,
relationships per type, total relationships, total compiler objects,
validation/enrichment/normalization/reference-resolution summaries).
Both are plain dicts, matching every earlier phase's own "plain, storable
dict" convention (see compiler/validation.py's own ValidationReport.to_dict()
precedent).

COMPILER_STATUS FIELDS -- what they do and do not mean: `validation_status`
and `compiler_status` both simply carry forward
validation_report["status"] ("pass"/"fail") -- the ONLY status judgment
this compiler currently computes anywhere is Phase B4's validation pass,
so `compiler_status` is that same verdict, exposed under the compiler-
build-level key name the manifest's own field list calls for, not a
second, independently-computed judgment. `build_status` is narrower
still: it only ever reports whether THIS manifest-generation pass itself
completed ("generated") -- it is not a readiness verdict, not a
fingerprint, and not a signal that the compiler IR is fit for any
particular downstream use. Phase B5.2/B5.3's own Compiler Readiness
milestone is what will eventually answer that broader question; this
module deliberately does not anticipate it.

DISAMBIGUATION (post-B5.3 audit refinement): compiler/finalize.py's
CompilerBuildSummary ALSO exposes a field named `build_status`, but with
a different meaning entirely -- there, `build_status` carries the final
READY / READY_WITH_WARNINGS / FAILED verdict (see that module's TASK 2).
`CompilerManifest.build_status` (this module) and
`CompilerBuildSummary.build_status` (finalize.py) are therefore two
same-named fields with two different meanings on two different
artifacts. To avoid ambiguity, this manifest now ALSO exposes the exact
same value under the unambiguous name `manifest_generation_status`; new
code should prefer that field. The original `build_status` field is left
in place, unchanged, purely for backward compatibility with existing
callers/tests -- it is not removed or renamed.

registry_versions IS NOT a per-registry map (there is no meaningful
notion of "this ConceptRegistry is on version X" separate from every
other registry) -- it is a map of PASS NAME -> that pass's own existing
version marker (ENRICHMENT_VERSION, NORMALIZATION_VERSION,
REFERENCE_RESOLUTION_VERSION, RELATIONSHIP_RESOLUTION_VERSION,
VALIDATION_VERSION), each imported unchanged from the module that already
owns it -- exactly the "reuse, don't duplicate" rule applied to
versioning.

PIPELINE INTEGRATION: generate_compiler_manifest() is the one pipeline.py
integration point (mirrors validate_compiler_state()'s own shape). It
must run AFTER compiler.validation.validate_compiler_state() (so there is
a validation report to read status/summaries from) and BEFORE
compiler_state.set_current_registry_manager() (so this manifest describes
`registry_manager` exactly as it is about to become "current", not a
stale snapshot) -- see pipeline.py's own integration comment at the call
site. The manifest and statistics are handed to compiler_state.
set_current_compiler_manifest() / set_current_compiler_statistics()
immediately after (this phase's own additions to compiler/state.py --
see that module's docstring), making them "part of Compiler State" per
the task spec, WITHOUT writing either into ChapterJSON or onto `manager`
itself.

BACKWARD COMPATIBILITY: every field this module reads (from
`validation_report`, from `manager.statistics()`, from every earlier
phase's own *_VERSION/*_FIELDS constant, from config.SCHEMA_VERSION) is
only ever read, never changed. No existing registry, field, relationship,
or Chapter JSON output changes as a result of this module existing. The
only new compiler artifacts are the manifest and statistics dicts
themselves (plus the four small, additive get/set/has functions in
compiler/state.py that hold them).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import SCHEMA_VERSION

from .registry_manager import RegistryManager
from .enrichment import ENRICHMENT_VERSION, ENRICHMENT_FIELDS
from .normalization import NORMALIZATION_VERSION, NORMALIZATION_FIELDS
from .references import REFERENCE_RESOLUTION_VERSION, REFERENCE_FIELDS
from .relationships import (
    RELATIONSHIP_RESOLUTION_VERSION,
    RELATIONSHIP_REGISTRY_NAME,
)
from .validation import VALIDATION_VERSION

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This compiler's own overall pipeline version -- independent of
# ENRICHMENT_VERSION/NORMALIZATION_VERSION/REFERENCE_RESOLUTION_VERSION/
# RELATIONSHIP_RESOLUTION_VERSION/VALIDATION_VERSION (which each version
# their own separate pass) and independent of config.SCHEMA_VERSION
# (which versions Chapter JSON's own schema, not the compiler pipeline
# that produces the IR). Bump only when the overall compiler pipeline
# reaches a new milestone -- mirrors ENRICHMENT_VERSION's/
# NORMALIZATION_VERSION's own "B1b.2"/"B1c.1" milestone-name convention.
COMPILER_VERSION = "B5.1"

# This module's own version marker (independent of every earlier phase's
# own *_VERSION constant, which versions those separate passes). Bump
# only if the manifest/statistics SHAPE this file produces itself
# changes in a way a consumer of `manifest["build_version"]` should be
# able to detect.
BUILD_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Task 1: Compiler Manifest
# --------------------------------------------------------------------------

@dataclass
class CompilerManifest:
    """The full Phase B5.1 manifest artifact -- see module docstring's
    MANIFEST vs STATISTICS section. Purely a data holder; all the actual
    derivation happens in generate_compiler_manifest() below, which reads
    already-computed compiler state and folds it into one of these.
    Field set is exactly the task's own "Include at minimum" list, plus
    `generated_at` (additive, matching ValidationReport's own
    convention)."""

    generated_at: str
    compiler_version: str
    schema_version: str
    build_version: str
    chapter_identifier: Optional[str]
    registry_versions: Dict[str, str]
    registry_count: int
    object_count: int
    relationship_count: int
    validation_status: str
    compiler_status: str
    build_status: str
    manifest_generation_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compiler_manifest(
    manager: RegistryManager,
    validation_report: Dict[str, Any],
    *,
    chapter_identifier: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase B5.1 Task 1 / Task 4's single pipeline.py integration point
    (mirrors compiler.validation.validate_compiler_state()'s own shape).
    Must run AFTER validate_compiler_state() (so `validation_report` is
    available to read from) and BEFORE
    compiler_state.set_current_registry_manager() -- see module
    docstring's PIPELINE INTEGRATION section and pipeline.py's own
    comment at the call site.

    Read-only over `manager` and `validation_report`: no registry is
    inserted into, updated, or removed from; no item dict anywhere is
    mutated; `validation_report` is only ever read. Every count below is
    read from `validation_report["statistics"]` (already computed by
    validate_compiler_state()) where available, falling back to
    `manager`'s own cheap aggregate accessors (`.names()`, `.total_size()`)
    only if a caller supplies a `validation_report` that does not carry
    the expected `statistics` block (e.g. a hand-built test fixture) --
    never by iterating every registry's items itself.

    Returned as a plain dict (manifest.to_dict()) for the same
    "plain, storable dict" reasons validate_compiler_state() already
    documents for its own return value, and so it can be handed directly
    to compiler_state.set_current_compiler_manifest() (task's own "the
    manifest belongs to Compiler State").
    """
    stats = validation_report.get("statistics") or {}
    relationship_summary = validation_report.get("relationship_summary") or {}
    status = validation_report.get("status", "unknown")

    manifest = CompilerManifest(
        generated_at=datetime.now(timezone.utc).isoformat(),
        compiler_version=COMPILER_VERSION,
        schema_version=SCHEMA_VERSION,
        build_version=BUILD_VERSION,
        chapter_identifier=chapter_identifier,
        registry_versions={
            "enrichment": ENRICHMENT_VERSION,
            "normalization": NORMALIZATION_VERSION,
            "reference_resolution": REFERENCE_RESOLUTION_VERSION,
            "relationship_resolution": RELATIONSHIP_RESOLUTION_VERSION,
            "validation": VALIDATION_VERSION,
        },
        registry_count=stats.get("registries_checked", len(manager.names())),
        object_count=stats.get("total_canonical_objects", manager.total_size()),
        relationship_count=stats.get(
            "total_relationships", relationship_summary.get("total", 0)
        ),
        validation_status=status,
        # `compiler_status` is the same Phase B4 verdict, exposed under
        # the manifest's own key name -- see module docstring's
        # COMPILER_STATUS FIELDS section for why this is a carry-forward,
        # not a second independently-computed judgment.
        compiler_status=status,
        # Reports only that manifest generation itself completed -- see
        # module docstring's COMPILER_STATUS FIELDS section for why this
        # is deliberately NOT a readiness verdict. Kept, unchanged, for
        # backward compatibility with every existing caller/test that
        # already reads `manifest["build_status"]`.
        build_status="generated",
        # Identical value to `build_status` above, exposed under an
        # unambiguous name. Audit finding: two different compiler
        # artifacts both expose a field called `build_status` with
        # different meanings -- CompilerManifest's own ("manifest
        # generation completed") vs CompilerBuildSummary's own (the
        # final READY/READY_WITH_WARNINGS/FAILED verdict, see
        # compiler/finalize.py). Rather than rename or remove the
        # existing `build_status` field (a breaking change for any
        # existing consumer/test), this manifest additionally exposes
        # the same value under `manifest_generation_status`, which is
        # the name new code should prefer. `build_status` remains for
        # backward compatibility only.
        manifest_generation_status="generated",
    )
    return manifest.to_dict()


# --------------------------------------------------------------------------
# Task 2: Compiler Statistics
# --------------------------------------------------------------------------

@dataclass
class CompilerStatistics:
    """The full Phase B5.1 statistics artifact -- see module docstring's
    MANIFEST vs STATISTICS section. Purely a data holder; all the actual
    derivation happens in generate_compiler_statistics() below."""

    generated_at: str
    registry_sizes: Dict[str, int]
    relationships_by_type: Dict[str, int]
    total_relationships: int
    total_objects: int
    validation_summary: Dict[str, Any]
    enrichment_summary: Dict[str, Any]
    normalization_summary: Dict[str, Any]
    reference_resolution_summary: Dict[str, Any]
    relationship_resolution_summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compiler_statistics(
    manager: RegistryManager,
    validation_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase B5.1 Task 2. Same reuse rule as generate_compiler_manifest()
    above: every count/summary below is read from `validation_report`
    (already computed by validate_compiler_state()) or from
    `manager.statistics()` (RegistryManager's own cheap, counter-backed
    aggregate -- see compiler/registry_manager.py; not a rescan of every
    item). Read-only over both arguments.

    `objects per registry` / `registry sizes` (task's own two example
    bullets) are the SAME fact -- how many items each registry currently
    holds -- so both are represented by the one `registry_sizes` field
    below rather than two separately-computed, always-identical dicts.
    """
    stats = validation_report.get("statistics") or {}
    reference_summary = validation_report.get("reference_summary") or {}
    relationship_summary = validation_report.get("relationship_summary") or {}
    status = validation_report.get("status", "unknown")

    registry_sizes = {
        name: registry_stats.size
        for name, registry_stats in manager.statistics().items()
    }

    statistics = CompilerStatistics(
        generated_at=datetime.now(timezone.utc).isoformat(),
        registry_sizes=registry_sizes,
        relationships_by_type=dict(relationship_summary.get("by_type") or {}),
        total_relationships=relationship_summary.get(
            "total", stats.get("total_relationships", 0)
        ),
        total_objects=stats.get("total_canonical_objects", manager.total_size()),
        validation_summary={
            "status": status,
            **stats,
        },
        enrichment_summary={
            "version": ENRICHMENT_VERSION,
            "fields": list(ENRICHMENT_FIELDS),
        },
        normalization_summary={
            "version": NORMALIZATION_VERSION,
            "fields": list(NORMALIZATION_FIELDS),
        },
        reference_resolution_summary={
            "version": REFERENCE_RESOLUTION_VERSION,
            "fields": list(REFERENCE_FIELDS),
            **reference_summary,
        },
        relationship_resolution_summary={
            "version": RELATIONSHIP_RESOLUTION_VERSION,
            "registry_name": RELATIONSHIP_REGISTRY_NAME,
            **relationship_summary,
        },
    )
    return statistics.to_dict()