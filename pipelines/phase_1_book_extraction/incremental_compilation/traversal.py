"""
incremental_compilation/traversal.py — Phase E4: Dependency Graph
Traversal (Rebuild Order).

SCOPE: `compute_rebuild_order()` REUSES Phase E2's own DependencyGraph
(`dependency_graph.build.generate_dependency_graph()`'s output) purely
as read-only data to traverse -- it never rebuilds it, never modifies
it, and never inserts into, updates, or removes from any
compiler_registry.CanonicalRegistry it came from (task's own "Reuse the
Build Dependency Graph. Never rebuild it. Never modify it. Only
traverse it."). It answers a DIFFERENT question than Phase E3's own
change_detection.traversal.compute_affected_artifacts(): that function
finds an unordered SET of affected artifacts; this function takes a
SET Phase E4's own planner.py already determined must be rebuilt (dirty
union affected -- reused from E3/planner.py, never re-derived here) and
answers "in what ORDER can these be rebuilt without ever rebuilding an
artifact before something it depends on." Neither E2 nor E3 ever
computes this ordering -- this is Phase E4's own, new contribution.

DIRECTION: dependency_graph.edge's own convention (edge.py's own module
docstring, reused unchanged here) is that one `DependencyEdge` reads
"`source_node_id` depends_on `target_node_id`" -- i.e. `target_node_id`
was built first and `source_node_id` consumed it. A valid rebuild order
is therefore any ordering where, for every edge between two nodes both
in the rebuild set, `target_node_id` appears before `source_node_id`.
This module computes that via Kahn's algorithm (in-degree counting +
zero-in-degree frontier), restricted to edges whose BOTH endpoints are
in the given `node_ids` set -- an edge to/from an artifact outside the
rebuild set carries no ordering constraint Phase E4 needs to satisfy
(that artifact is not being rebuilt this run).

ARTIFACT KEYS NOT MODELED AS A DEPENDENCYNODE: Phase E3's own snapshot
(change_detection/snapshot.py) adds two synthetic artifact keys with no
DependencyNode of their own in Phase E2's graph -- "configuration" and
"dependency_graph" (see that module's own CONFIGURATION AND
DEPENDENCY-GRAPH KEYS section). Such a key, if present in `node_ids`,
simply has no edges in `dependency_graph` (it is absent from both
`source_node_id` and `target_node_id` in every edge) -- Kahn's
algorithm below treats it exactly like any other zero-in-degree,
zero-out-degree node: it enters the frontier immediately and is placed
according to the same deterministic, alphabetical tie-break every other
unconstrained node gets. No special-case code is needed for this; it
falls out of the general algorithm.

DETERMINISM: the zero-in-degree frontier is a sorted structure (not a
plain set/list pop, which would be insertion-order- or
hash-order-dependent) -- the same node_id, in the same rebuild set,
with the same DependencyGraph, always produces the same order, on this
run and every future one.

CYCLES: Phase E2 performs no cycle check on the DependencyGraph it
builds (explicitly out of E2's own scope). In the ordinary case, E2's
own edges are constructed strictly downstream (see dependency_graph/
build.py's own DEPENDENCY SHAPE section), so no cycle should ever
appear among a real DependencyGraph's nodes -- but this module does not
assume that invariant holds across a future Phase E2 change it hasn't
seen. If Kahn's algorithm terminates with nodes remaining unordered (a
cycle), those remaining nodes are appended in deterministic,
alphabetically-sorted order to the end of the returned order (never
raised -- Phase E4 is a read-only planning pass, and a graph anomaly
must degrade to "still produce a deterministic, if imperfectly
ordered, plan" rather than abort the chapter's build; see
incremental_compilation.exceptions.RebuildOrderCycleError's own
NOTE ON ACTUAL RUNTIME BEHAVIOUR). The caller (planner.py) is told
whether a cycle was hit via this function's own returned
`cycle_detected` flag, and surfaces that as an `errors` entry on the
final IncrementalCompilationPlan.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple


def _rebuild_subgraph_edges(
    dependency_graph: Any, node_ids: Set[str]
) -> List[Tuple[str, str]]:
    """Returns every (source_node_id, target_node_id) pair from Phase
    E2's own `edges` list where BOTH endpoints are in `node_ids`.
    Read-only over `dependency_graph`; never mutates it. Malformed/
    missing edge endpoints (should not occur -- Phase E2's own
    `_edge_if()` only ever builds edges between two real node_ids --
    but this module does not assume that invariant holds across a
    future Phase E2 change it hasn't seen) are skipped rather than
    raising, mirroring change_detection.traversal._reverse_adjacency()'s
    own precedent."""
    edges = (dependency_graph or {}).get("edges") or []
    pairs: List[Tuple[str, str]] = []
    for edge in edges:
        source = edge.get("source_node_id")
        target = edge.get("target_node_id")
        if source is None or target is None:
            continue
        if source in node_ids and target in node_ids:
            pairs.append((source, target))
    return pairs


def compute_rebuild_order(
    dependency_graph: Any, node_ids: Iterable[str]
) -> Dict[str, Any]:
    """Computes a deterministic topological rebuild order for
    `node_ids` (Phase E4's own rebuild set -- dirty union affected,
    already determined by planner.py, never re-derived here), walking
    Phase E2's own DependencyGraph edges read-only (module docstring).

    Returns:
        {
            "order": List[str],           # node_ids in a valid
                                            # dependency-respecting
                                            # rebuild order (or, for
                                            # any node(s) caught in a
                                            # cycle, a deterministic
                                            # alphabetical fallback --
                                            # see module docstring's
                                            # CYCLES section)
            "cycle_detected": bool,
            "cycle_node_ids": List[str],   # empty unless cycle_detected
            "edges_considered": int,       # size of the rebuild
                                            # subgraph actually walked
        }

    Deterministic: same DependencyGraph + same node_ids -> same
    `order`, on this run and every future one, regardless of edge-list
    or node_ids iteration order (module docstring's DETERMINISM
    section)."""
    remaining: Set[str] = set(node_ids)
    if not remaining:
        return {
            "order": [],
            "cycle_detected": False,
            "cycle_node_ids": [],
            "edges_considered": 0,
        }

    subgraph_edges = _rebuild_subgraph_edges(dependency_graph, remaining)

    # `dependents[target] = [source, ...]`: nodes that depend on
    # `target` (i.e. `target` must be ordered before each of them).
    # `blockers_remaining[source] = count of targets not yet ordered`:
    # Kahn's algorithm's own in-degree, counted over this "must precede"
    # relation (an edge's `target_node_id` is the predecessor here, its
    # `source_node_id` the successor -- see module docstring's
    # DIRECTION section).
    dependents: Dict[str, List[str]] = {node_id: [] for node_id in remaining}
    blockers_remaining: Dict[str, int] = {node_id: 0 for node_id in remaining}
    for source, target in subgraph_edges:
        dependents[target].append(source)
        blockers_remaining[source] += 1

    order: List[str] = []
    # Deterministic frontier: every node currently un-blocked, kept
    # sorted so the tie-break between two simultaneously-ready nodes is
    # always alphabetical, never dict/set iteration order.
    frontier: List[str] = sorted(
        node_id for node_id, count in blockers_remaining.items() if count == 0
    )

    while frontier:
        current = frontier.pop(0)
        remaining.discard(current)
        order.append(current)
        newly_ready: List[str] = []
        for dependent in sorted(dependents.get(current, [])):
            blockers_remaining[dependent] -= 1
            if blockers_remaining[dependent] == 0:
                newly_ready.append(dependent)
        if newly_ready:
            # Re-sort rather than append+assume-sorted: `frontier` may
            # already hold entries from an earlier iteration: a plain
            # append would not preserve global alphabetical ordering
            # across iterations.
            frontier = sorted(frontier + newly_ready)

    cycle_detected = bool(remaining)
    cycle_node_ids = sorted(remaining)
    if cycle_detected:
        # Deterministic fallback -- see module docstring's CYCLES
        # section: never raise, always still produce a complete,
        # deterministic order.
        order.extend(cycle_node_ids)

    return {
        "order": order,
        "cycle_detected": cycle_detected,
        "cycle_node_ids": cycle_node_ids,
        "edges_considered": len(subgraph_edges),
    }