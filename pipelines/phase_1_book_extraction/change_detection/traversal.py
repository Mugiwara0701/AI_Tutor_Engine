"""
change_detection/traversal.py — Phase E3: Dependency Graph Traversal.

SCOPE: `compute_affected_artifacts()` REUSES Phase E2's own
DependencyGraph (`dependency_graph.build.generate_dependency_graph()`'s
output) purely as read-only data to traverse -- it never rebuilds it,
never modifies it, and never inserts into, updates, or removes from any
compiler_registry.CanonicalRegistry it came from (task's own "Reuse the
Build Dependency Graph. Never rebuild it. Never modify it."). It answers
exactly one question: given a set of artifact node_ids already known to
have changed (added or modified -- see engine.py, this module's only
caller), which OTHER currently-modeled artifacts transitively depend on
one of them?

DIRECTION: dependency_graph.edge's own convention (edge.py's own module
docstring) is that one `DependencyEdge` reads "`source_node_id` depends
on `target_node_id`" -- i.e. `target_node_id` was built first and
`source_node_id` consumed it. An artifact is therefore "affected" by a
change at node X if it is reachable by walking from X against edge
direction (target -> its dependents' source_node_id), transitively --
NOT the other way around. This module builds that one reverse-adjacency
index once per call and reuses it for every changed node in the input
set, rather than re-scanning the edge list per node.

REMOVED ARTIFACTS ARE NOT TRAVERSED: an artifact_key present in a
previous build but absent from the CURRENT DependencyGraph has, by
definition, no node in the graph this module traverses -- there is
nothing to walk from. A removed artifact's downstream impact (if any)
is a Phase E4/E5 concern (dependency-integrity validation), explicitly
out of Phase E3's own scope -- see this package's own __init__.py
docstring's WHAT THIS IS NOT section.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _reverse_adjacency(dependency_graph: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Builds `{target_node_id: [source_node_id, ...]}` from Phase E2's
    own `edges` list -- i.e. for every artifact, the list of artifacts
    that directly depend on it. Read-only over `dependency_graph`;
    never mutates it. Malformed/missing edge endpoints (should not
    occur -- Phase E2's own `_edge_if()` only ever builds edges between
    two real node_ids -- but this module does not assume that
    invariant holds across a future Phase E2 change it hasn't seen) are
    skipped rather than raising, since a malformed edge is a Phase E2
    concern this read-only pass has no business failing on."""
    adjacency: Dict[str, List[str]] = {}
    edges = (dependency_graph or {}).get("edges") or []
    for edge in edges:
        target = edge.get("target_node_id")
        source = edge.get("source_node_id")
        if target is None or source is None:
            continue
        adjacency.setdefault(target, []).append(source)
    return adjacency


def compute_affected_artifacts(
    dependency_graph: Optional[Dict[str, Any]],
    changed_node_ids: Iterable[str],
) -> List[str]:
    """Traverses Phase E2's own DependencyGraph (read-only, never
    rebuilt, never modified -- module docstring) to find every artifact
    that transitively depends on one of `changed_node_ids`. Returns a
    sorted list, EXCLUDING every id already in `changed_node_ids`
    itself (an artifact is either "changed" or "affected by a change",
    never double-counted as both by this module -- see engine.py, which
    keeps the two sets disjoint in the final report).

    Deterministic: same DependencyGraph + same changed_node_ids ->
    same sorted output, on this run and every future one, regardless of
    edge-list iteration order (an explicit BFS frontier, not a
    dict-ordering-dependent walk)."""
    changed = set(changed_node_ids)
    if not changed:
        return []

    adjacency = _reverse_adjacency(dependency_graph)

    visited: set = set()
    frontier: List[str] = list(changed)
    while frontier:
        current = frontier.pop()
        for dependent in adjacency.get(current, ()):
            if dependent in changed or dependent in visited:
                continue
            visited.add(dependent)
            frontier.append(dependent)

    return sorted(visited)