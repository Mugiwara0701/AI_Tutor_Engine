"""
artifact_manager/build.py — Phase F2: the canonical, immutable Build
object.

WHAT "REFERENCE" MEANS HERE (read this before touching the
*_reference fields below): F0's frozen contract requires Build to
"reference existing compiler artifacts" and "never duplicate them".
Phases A-E1/E2/E3/E4/E5 already produce a Compiler IR (RegistryManager),
a Knowledge Graph, Build Metadata, a Dependency Graph, a Change
Detection Report, an Incremental Plan, Incremental Validation, and
Incremental Finalization -- but every one of those artifacts is, by
existing and FROZEN design, chapter-scoped: each is held only in that
phase's own module-level "current chapter" state slot (compiler.state,
knowledge_graph.state, build_metadata.state, dependency_graph.state,
change_detection.state, incremental_compilation.state,
incremental_compilation_validation.state,
incremental_compilation_finalization.state), reset at the start of the
NEXT chapter, and explicitly never attached to the written Chapter JSON
(see e.g. build_metadata's own pipeline.py integration comment: "nothing
here is attached to chapter_dict ... internal diagnostic, never
serialized into Chapter JSON"). Phases A-E1 never persist these
artifacts anywhere durable, and Phase F2 does not redesign Phases A-E1
to make them do so (F0 §13's "Phase F MUST NOT ... redesign previous
phases").

Given that, a Build spanning a whole CompilerRuntime.run() -- which may
process any number of books and any number of chapters within them --
has no single "the" Compiler IR / Knowledge Graph / ... to duplicate;
the only artifact those phases' own state modules can honestly offer
Phase F2 is a *snapshot of whichever chapter was most recently
processed when book_orchestrator.run() returned* (an ordinary read of
each phase's already-public get_current_*()/has_current_*() accessors,
performed once, immediately, before the next run() would reset them --
i.e. exactly "consuming" state the way runtime/state.py's own module
docstring already describes Phase F's relationship to chapter-scoped
state). build_reference_snapshot() below does exactly that read and
nothing more: no recomputation, no new persistence of Phase A-E1
internals, one read of each existing accessor.

Each `*_reference` field on Build is therefore one of:
  * None -- no chapter ever completed this run (zero books/chapters
    processed, or the run failed before any chapter finished), so
    there is nothing to reference.
  * a dict of shape {"source": "last_processed_chapter",
    "artifact": <that phase's own already-computed dict>} -- the last
    chapter processed this run's own artifact, read verbatim (via
    to_dict() where the accessor returns a dataclass rather than an
    already-plain dict) from that phase's existing state module.

This is a deliberate, narrower reading of "reference" than "one
reference per chapter this run touched" would be -- an honest
consequence of Phases A-E1's own chapter-scoped state design, not a
gap Phase F2 papers over. The Build Manifest's own `artifact_locations`
(see manifest.py) is what carries the comprehensive, per-chapter record
of this run's real, durable output (every chapter JSON path and book
manifest path book_orchestrator/pipeline.py actually wrote), since that
IS available for every chapter, not just the last one.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .exceptions import BuildError

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase, bumped only if the SHAPE this
# module produces changes in a way a consumer should be able to detect.
BUILD_VERSION = "F2.1"


def _to_plain(value: Any) -> Any:
    """Normalizes one phase's get_current_*() result into a plain,
    JSON-safe dict: already-a-dict is returned as-is, a dataclass
    exposing to_dict() is converted via that method, None stays None.
    Never re-derives a field -- purely a shape adapter so Build stays
    trivially serializable via the exact same json.dumps() every other
    artifact in this codebase already goes through."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    # Last resort for a plain dataclass instance with no to_dict() of
    # its own -- still no recomputation, just a shape adapter.
    try:
        return asdict(value)
    except TypeError:
        return value


def _reference(artifact: Any) -> Optional[Dict[str, Any]]:
    """Wraps one already-computed chapter-scoped artifact (or None) into
    this Build's own `*_reference` shape. See module docstring."""
    plain = _to_plain(artifact)
    if plain is None:
        return None
    return {"source": "last_processed_chapter", "artifact": plain}


@dataclass(frozen=True)
class ReferenceSnapshot:
    """Every chapter-scoped artifact reference a Build carries, read
    once (see build_reference_snapshot() below) immediately after
    book_orchestrator.run() returns. Purely a data holder -- no field
    here is computed, only read and shape-adapted (see _reference()
    above)."""

    compiler_ir_reference: Optional[Dict[str, Any]]
    knowledge_graph_reference: Optional[Dict[str, Any]]
    dependency_graph_reference: Optional[Dict[str, Any]]
    build_metadata_reference: Optional[Dict[str, Any]]
    change_detection_reference: Optional[Dict[str, Any]]
    incremental_plan_reference: Optional[Dict[str, Any]]
    incremental_validation_reference: Optional[Dict[str, Any]]
    incremental_finalization_reference: Optional[Dict[str, Any]]


def build_reference_snapshot() -> ReferenceSnapshot:
    """Reads every Phase A-E1 "current chapter" state accessor exactly
    once, wraps each into this Build's `*_reference` shape, and returns
    them together. Called by create_build() immediately after
    book_orchestrator.run() returns and before anything else in this
    process could start a new chapter (which would reset these slots) --
    see module docstring for why this is a read, not a redesign, of
    Phases A-E1's own existing state modules.

    Local imports, mirroring runtime/runtime.py's own local
    `import book_orchestrator`: avoids forcing an import-order
    dependency between artifact_manager and every phase package at
    artifact_manager's own module-load time."""
    import compiler.state as compiler_state
    import knowledge_graph.state as knowledge_graph_state
    import dependency_graph.state as dependency_graph_state
    import build_metadata.state as build_metadata_state
    import change_detection.state as change_detection_state
    import incremental_compilation.state as incremental_compilation_state
    import incremental_compilation_validation.state as incremental_compilation_validation_state
    import incremental_compilation_finalization.state as incremental_compilation_finalization_state

    return ReferenceSnapshot(
        compiler_ir_reference=_reference(
            compiler_state.get_current_registry_manager().serialize()
            if compiler_state.has_current_registry_manager() else None
        ),
        knowledge_graph_reference=_reference(
            knowledge_graph_state.get_current_knowledge_graph_manifest()
            if knowledge_graph_state.has_current_knowledge_graph_manifest() else None
        ),
        dependency_graph_reference=_reference(
            dependency_graph_state.get_current_dependency_graph()
        ),
        build_metadata_reference=_reference(
            build_metadata_state.get_current_build_metadata()
        ),
        change_detection_reference=_reference(
            change_detection_state.get_current_change_detection_report()
        ),
        incremental_plan_reference=_reference(
            incremental_compilation_state.get_current_incremental_compilation_plan()
        ),
        incremental_validation_reference=_reference(
            incremental_compilation_validation_state.get_current_incremental_compilation_validation_report()
        ),
        incremental_finalization_reference=_reference(
            incremental_compilation_finalization_state.get_current_incremental_compilation_readiness_report()
        ),
    )


def _generate_build_id(started_at: datetime) -> str:
    """Deterministic-shape, collision-resistant build id:
    "build-<UTC compact timestamp>-<short uuid4 suffix>". Timestamp
    first so build ids sort chronologically by construction (same
    "identifier is naturally orderable" property compiler/knowledge_graph
    ids already have via their own identity.py modules); the uuid4
    suffix (not a hash of build contents) is what actually guarantees
    uniqueness for two builds started in the same second, mirroring
    this codebase's existing precedent of using uuid4 for exactly this
    "identity, not content-derived" purpose (see e.g.
    knowledge_graph.identity's own node/edge id generation)."""
    stamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"build-{stamp}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class Build:
    """The canonical, immutable record of one CompilerRuntime run() (or
    resume()) call. Every field is either read verbatim from this run's
    own book_orchestrator.run() output (execution_summary,
    runtime_metadata) or from Phases A-E1's own existing chapter-scoped
    state (the eight `*_reference` fields -- see module docstring), plus
    this Build's own identity (build_id) and its Build Manifest
    (build_manifest, attached by manifest.py's generate_build_manifest()
    -- see with_manifest() below, since a Build is immutable and its
    manifest can only be computed from an already-fully-built Build).

    Never mutated after construction: `with_manifest()` returns a NEW
    Build (dataclasses.replace-style), it does not mutate `self` --
    same "immutable record, replace don't mutate" contract this
    dataclass's own `frozen=True` already enforces at the language
    level.
    """

    build_id: str
    build_manifest: Optional[Dict[str, Any]]

    compiler_ir_reference: Optional[Dict[str, Any]]
    knowledge_graph_reference: Optional[Dict[str, Any]]
    dependency_graph_reference: Optional[Dict[str, Any]]
    build_metadata_reference: Optional[Dict[str, Any]]
    change_detection_reference: Optional[Dict[str, Any]]
    incremental_plan_reference: Optional[Dict[str, Any]]
    incremental_validation_reference: Optional[Dict[str, Any]]
    incremental_finalization_reference: Optional[Dict[str, Any]]

    runtime_metadata: Dict[str, Any]
    execution_summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def with_manifest(self, build_manifest: Dict[str, Any]) -> "Build":
        """Returns a new Build with `build_manifest` attached -- the
        only way a Build's `build_manifest` field is ever set, since
        generate_build_manifest() (manifest.py) needs an already-
        constructed Build to summarize in the first place."""
        return Build(
            build_id=self.build_id,
            build_manifest=build_manifest,
            compiler_ir_reference=self.compiler_ir_reference,
            knowledge_graph_reference=self.knowledge_graph_reference,
            dependency_graph_reference=self.dependency_graph_reference,
            build_metadata_reference=self.build_metadata_reference,
            change_detection_reference=self.change_detection_reference,
            incremental_plan_reference=self.incremental_plan_reference,
            incremental_validation_reference=self.incremental_validation_reference,
            incremental_finalization_reference=self.incremental_finalization_reference,
            runtime_metadata=self.runtime_metadata,
            execution_summary=self.execution_summary,
        )


def create_build(
    *,
    context: Any,
    status: str,
    all_stats: List[Dict[str, Any]],
    error: Optional[str],
    started_at: datetime,
    finished_at: Optional[datetime] = None,
) -> Build:
    """Builds this run's Build object. Called once by CompilerRuntime._
    execute() (runtime/runtime.py), immediately after book_orchestrator.
    run() returns (or raises -- see runtime/runtime.py's own error-
    propagation contract; create_build() is only called on the success/
    cancelled path, a FAILED run still gets a Build so history/discovery
    can show it failed, see runtime/runtime.py).

    `context`: this run's runtime.context.ExecutionContext (the exact
        use_vlm/page_batch_size/force/pdf_input_folder snapshot
        CompilerRuntime already builds -- reused verbatim, not
        recomputed).
    `status`: this run's final runtime.context.RuntimeStatus string
        (COMPLETED/CANCELLED/FAILED).
    `all_stats`: book_orchestrator.run()'s own return value -- one dict
        per book, unchanged.
    `error`: str(exc) if status is FAILED, else None -- same value
        runtime.state.get_current_error() already holds.
    `started_at`/`finished_at`: this run's wall-clock bounds (UTC).

    Raises BuildError if `all_stats` is not a list (a caller/programming
    error -- book_orchestrator.run() always returns a list, even an
    empty one).
    """
    if not isinstance(all_stats, list):
        raise BuildError(
            f"create_build(): all_stats must be a list of per-book stats "
            f"dicts (book_orchestrator.run()'s own return shape), got "
            f"{type(all_stats).__name__}."
        )

    finished_at = finished_at or datetime.now(timezone.utc)

    books_completed = len(all_stats)
    chapters_written = sum(s.get("written", 0) for s in all_stats)
    chapters_found = sum(s.get("found", 0) for s in all_stats)
    chapters_failed = sum(s.get("failed", 0) for s in all_stats)
    books_with_errors = [s.get("book_name") or s.get("book_title") for s in all_stats if s.get("error")]

    execution_summary: Dict[str, Any] = {
        "books_completed": books_completed,
        "chapters_found": chapters_found,
        "chapters_written": chapters_written,
        "chapters_failed": chapters_failed,
        "books_with_errors": books_with_errors,
        "status": status,
        "error": error,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
    }

    runtime_metadata: Dict[str, Any] = {
        "use_vlm": getattr(context, "use_vlm", None),
        "page_batch_size": getattr(context, "page_batch_size", None),
        "force": getattr(context, "force", None),
        "pdf_input_folder": getattr(context, "pdf_input_folder", None),
        "build_version": BUILD_VERSION,
    }

    snapshot = build_reference_snapshot()
    build_id = _generate_build_id(started_at)

    return Build(
        build_id=build_id,
        build_manifest=None,
        compiler_ir_reference=snapshot.compiler_ir_reference,
        knowledge_graph_reference=snapshot.knowledge_graph_reference,
        dependency_graph_reference=snapshot.dependency_graph_reference,
        build_metadata_reference=snapshot.build_metadata_reference,
        change_detection_reference=snapshot.change_detection_reference,
        incremental_plan_reference=snapshot.incremental_plan_reference,
        incremental_validation_reference=snapshot.incremental_validation_reference,
        incremental_finalization_reference=snapshot.incremental_finalization_reference,
        runtime_metadata=runtime_metadata,
        execution_summary=execution_summary,
    )
