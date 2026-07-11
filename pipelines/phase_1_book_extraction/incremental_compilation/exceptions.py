"""
incremental_compilation/exceptions.py — Phase E4: exception hierarchy
for the Incremental Compilation layer.

Mirrors change_detection/exceptions.py's own convention exactly, one
package over: small, specific exception classes so a caller can catch
precisely what it cares about instead of parsing free-text messages.
"""


class IncrementalCompilationError(Exception):
    """Base class for every error raised anywhere in the
    incremental_compilation package. Mirrors
    change_detection.exceptions.ChangeDetectionError's role as the one
    catch-all ancestor for its own layer."""


class InvalidChangeDetectionReportError(IncrementalCompilationError):
    """Describes a `change_detection_report` argument that is neither
    `None` nor a dict shaped like
    change_detection.report.ChangeDetectionReport's own output (i.e.
    missing one of its own list fields this package reads).

    NOTE ON ACTUAL RUNTIME BEHAVIOUR: mirrors change_detection.
    exceptions.InvalidPreviousBuildError's own precedent exactly --
    this class is instantiated (for its message) inside
    planner.plan_rebuild()'s own input-validation helper, but that
    helper always catches it itself and never lets it propagate -- like
    Phase E3, Phase E4 is a read-only reporting pass, and a malformed
    ChangeDetectionReport must degrade to "nothing known to plan"
    (str(exc) is appended to the returned plan's own `warnings` list)
    rather than abort the whole chapter's build."""

    def __init__(self, reason: str):
        super().__init__(
            f"incremental_compilation: invalid `change_detection_report` "
            f"argument -- {reason}"
        )
        self.reason = reason


class RebuildOrderCycleError(IncrementalCompilationError):
    """Describes a cycle detected among the artifacts requiring
    rebuild, while computing a topological rebuild order over Phase
    E2's own DependencyGraph (traversal.py).

    NOTE ON ACTUAL RUNTIME BEHAVIOUR: Phase E2's own build.py
    constructs edges strictly downstream (registry -> manifest ->
    statistics -> fingerprints -> ... -> build_metadata, see that
    module's own DEPENDENCY SHAPE section), so a cycle should never
    occur in practice -- but Phase E2 itself performs no cycle check
    (explicitly out of its own scope, see dependency_graph/build.py's
    own WHAT THIS IS NOT section), so Phase E4 cannot assume that
    invariant holds across a future Phase E2 change it hasn't seen.
    Exactly like InvalidChangeDetectionReportError above, this class is
    instantiated for its message but never allowed to propagate out of
    traversal.compute_rebuild_order() -- a detected cycle degrades to
    "the affected nodes are appended to the rebuild order in a
    deterministic, alphabetically-sorted fallback" plus an `errors`
    entry on the returned plan, never a raised exception that would
    abort the chapter's build."""

    def __init__(self, remaining_node_ids):
        self.remaining_node_ids = sorted(remaining_node_ids)
        super().__init__(
            "incremental_compilation: cycle detected in the rebuild "
            f"subgraph among: {self.remaining_node_ids!r}"
        )