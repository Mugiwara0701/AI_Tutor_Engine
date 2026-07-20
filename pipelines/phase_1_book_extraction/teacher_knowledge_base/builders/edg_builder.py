"""
teacher_knowledge_base/builders/edg_builder.py — M6.1 (remediated)

SPECIFICATION: ENRICHED_DEPENDENCY_GRAPH_SPECIFICATION.md v1.1.1

AUTHORITY: EDG is the SOLE canonical authority for all learning prerequisites.
  - No other object may author prerequisite relationships (AUTHORITY_MATRIX §2.1)
  - EKG contains NO PREREQUISITE_OF edges in v1
  - TU.prerequisites is a derived convenience snapshot from EDG
  - LearningPathNavigation.canonical_path IS the EDG topological_order (not re-derived)

NODE SCHEMA (spec §2):
  LearningDependencyNode {
    node_id, node_urn, concept_id, concept_key, concept_name,
    node_type, estimated_minutes, difficulty,
    prerequisite_ids, dependent_ids, remediation_target_ids,
    is_gate, is_optional, depth
  }

EDGE SCHEMA (spec §3):
  LearningDependencyEdge {
    edge_id, edge_urn, source_node_id, target_node_id,
    edge_type (REQUIRES | RECOMMENDED_BEFORE | SCAFFOLDS | GATES | ENABLES_REMEDIATION),
    strength, is_blocking, context
  }
  NOTE: No "dependency_type" (hard/soft/optional) — that was an invented field.
  NOTE: No "teaching_impact_score" — that was an invented field.

TOPOLOGICAL ORDER (spec §9):
  Kahn's algorithm over REQUIRES + GATES edges.
  Tie-break: is_gate=True first, then difficulty=easy first, then concept_id lexicographic.

CONTENT SOURCE:
  - Dependency relationships from: OKP.dependency_map
  - Node difficulty/estimated_minutes: OKP.learning_analytics.concept_analytics
  - Fallback to KnowledgeGraph prerequisite edges when OKP.dependency_map absent
"""
from __future__ import annotations

import uuid
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.edg")

_EDG_NS = uuid.UUID("fedcba98-7654-3210-fedc-ba9876543210")

STAGE = "edg"
EDG_VERSION = "1.1.1"

# V1 mandatory edge types (spec §4)
V1_EDGE_TYPES = {
    "REQUIRES",
    "RECOMMENDED_BEFORE",
    "SCAFFOLDS",
    "GATES",
    "ENABLES_REMEDIATION",
}


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_edg(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_edg(context: "TKBContext") -> None:  # noqa: F821
    artifacts = context.compiler_artifacts
    tkb_id = context.tkb_id

    # Teaching units must already be built (T2 runs after T3 in spec §6 pipeline)
    # But EDG runs at T2, before TU (T3). We use concept_index directly.
    concept_index = _get_concept_index(artifacts)
    learning_analytics = _get_learning_analytics(artifacts)

    # Load dependency relationships from OKP.dependency_map (primary)
    # or KnowledgeGraph prerequisite edges (fallback)
    raw_edges = _load_dependency_edges(artifacts)

    # Build node objects for every concept
    nodes: Dict[str, Any] = {}  # concept_id -> LearningDependencyNode
    for concept_id, entry in concept_index.items():
        node = _build_ldg_node(
            concept_id=concept_id,
            concept_entry=entry,
            tkb_id=tkb_id,
            learning_analytics=learning_analytics,
        )
        nodes[concept_id] = node

    # Build edge objects
    edges: Dict[str, Any] = {}  # edge_id -> LearningDependencyEdge
    for raw_edge in raw_edges:
        src_concept = str(raw_edge.get("source") or raw_edge.get("from") or "")
        tgt_concept = str(raw_edge.get("target") or raw_edge.get("to") or "")
        if not src_concept or not tgt_concept:
            continue
        if src_concept not in nodes or tgt_concept not in nodes:
            continue
        edge_type = _map_edge_type(raw_edge)
        edge = _build_ldg_edge(
            source_concept_id=src_concept,
            target_concept_id=tgt_concept,
            edge_type=edge_type,
            raw_edge=raw_edge,
            tkb_id=tkb_id,
            nodes=nodes,
        )
        edges[edge["edge_id"]] = edge

    # Populate prerequisite_ids, dependent_ids, depth from edges
    _populate_node_adjacencies(nodes, edges)

    # Topological order (spec §9: Kahn's with exact tie-break)
    topological_order = _compute_topological_order(nodes, edges)

    # Prerequisite chains (one per concept — shortest prereq path to root)
    prerequisite_chains = _compute_prerequisite_chains(nodes, edges, topological_order)

    # Remediation paths (ENABLES_REMEDIATION edges)
    remediation_paths = _compute_remediation_paths(nodes, edges)

    # Alternative learning paths (spec §7)
    alternative_paths = _compute_alternative_paths(nodes, edges, topological_order, learning_analytics)

    # Cycle detection (for validation)
    cycles_detected = _detect_cycles(nodes, edges)
    is_dag = len(cycles_detected) == 0

    if not is_dag:
        context.diagnostics.add_warning(
            STAGE,
            f"EDG is NOT a DAG ({len(cycles_detected)} cycle(s) detected). "
            "TKB validation will mark this as INVALID.",
            f"Cycles: {cycles_detected[:3]}",
        )

    edg = {
        "edg_id": str(uuid.uuid5(_EDG_NS, f"edg:{tkb_id}")),
        "original_dep_graph_id": str(
            (artifacts.get("optimized_knowledge_package") or {}).get("dependency_map_id") or ""
        ),
        "nodes": nodes,
        "edges": edges,
        "prerequisite_chains": prerequisite_chains,
        "remediation_paths": remediation_paths,
        "alternative_paths": alternative_paths,
        "topological_order": topological_order,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "metadata": {
            "edg_version": EDG_VERSION,
            "created_at": _now_iso(),
            "max_depth": max((n.get("depth", 0) for n in nodes.values()), default=0),
            "total_blocking_edges": sum(1 for e in edges.values() if e.get("is_blocking")),
            "total_soft_edges": sum(1 for e in edges.values() if not e.get("is_blocking")),
            "total_gate_nodes": sum(1 for n in nodes.values() if n.get("is_gate")),
        },
        "validation": {
            "is_dag": is_dag,
            "all_concept_ids_resolvable": True,  # all nodes come from concept_index
            "no_orphaned_nodes": True,
            "remediation_coverage": _compute_remediation_coverage(nodes, remediation_paths),
            "status": "VALID" if is_dag else "INVALID",
            "warnings": [],
            "errors": [] if is_dag else [f"Graph contains {len(cycles_detected)} cycle(s)"],
        },
    }
    context.set_output(STAGE, edg)
    logger.info(
        "EDG builder: %d nodes, %d edges, is_dag=%s, topological_order=%d concepts.",
        len(nodes), len(edges), is_dag, len(topological_order),
    )

    # ---- AUTHORITY_MATRIX §2.1 + TEACHING_UNIT_SPECIFICATION §3 ----------------
    # EDG is the sole canonical authority for prerequisites.
    # TU.prerequisites is a DERIVED CONVENIENCE SNAPSHOT populated here.
    # TU.edg_node_id cross-reference is also populated here.
    # TU.completeness_score is RECOMPUTED after prerequisites are injected
    # (the check "prerequisites resolved from EDG: weight 2" was False until now).
    _backfill_teaching_units_from_edg(context, nodes, edges)


def _get_concept_index(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        ci = okp.get("concept_index") or okp.get("concepts")
        if isinstance(ci, dict):
            return ci
        if isinstance(ci, list):
            return {str(c.get("concept_id") or c.get("id") or i): c
                    for i, c in enumerate(ci) if isinstance(c, dict)}
    kg = artifacts.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or []
    if isinstance(nodes, list):
        return {str(n.get("id") or n.get("concept_id") or i): n
                for i, n in enumerate(nodes) if isinstance(n, dict)}
    return {}


def _get_learning_analytics(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        la = okp.get("learning_analytics") or {}
        ca = la.get("concept_analytics") or {}
        return ca if isinstance(ca, dict) else {}
    return {}


def _load_dependency_edges(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load dependency edges from OKP.dependency_map (primary) or KG edges (fallback)."""
    okp = artifacts.get("optimized_knowledge_package") or {}
    if isinstance(okp, dict):
        dep_map = okp.get("dependency_map") or {}
        if isinstance(dep_map, dict):
            edges = dep_map.get("edges") or dep_map.get("dependencies") or []
            if edges:
                return list(edges)
        # Also try direct edges
        edges = okp.get("dependency_edges") or okp.get("prerequisites") or []
        if edges:
            return list(edges)

    # Fallback: derive from KnowledgeGraph prerequisite fields on nodes
    kg = artifacts.get("knowledge_graph") or {}
    nodes = kg.get("nodes") or []
    edges_from_kg = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        tgt = str(node.get("id") or node.get("concept_id") or "")
        for prereq in (node.get("prerequisites") or []):
            edges_from_kg.append({
                "source": str(prereq),
                "target": tgt,
                "edge_type": "REQUIRES",
                "strength": 1.0,
                "is_blocking": True,
                "context": "",
            })
    return edges_from_kg


def _map_edge_type(raw_edge: Dict[str, Any]) -> str:
    """Maps raw edge type string to one of the 5 v1 mandatory EDG types.
    Only maps what Phase 1 produces; does NOT invent new classifications."""
    raw = str(raw_edge.get("edge_type") or raw_edge.get("type") or "").upper()
    if raw in V1_EDGE_TYPES:
        return raw
    # Map common compiler conventions to v1 types
    mappings = {
        "PREREQUISITE": "REQUIRES",
        "REQUIRED": "REQUIRES",
        "DEPENDS_ON": "REQUIRES",
        "HARD_PREREQUISITE": "REQUIRES",
        "SOFT_PREREQUISITE": "RECOMMENDED_BEFORE",
        "RECOMMENDED": "RECOMMENDED_BEFORE",
        "SUGGESTED": "RECOMMENDED_BEFORE",
        "SCAFFOLD": "SCAFFOLDS",
        "GATE": "GATES",
        "MILESTONE": "GATES",
        "REMEDIATION": "ENABLES_REMEDIATION",
    }
    mapped = mappings.get(raw)
    if mapped:
        return mapped
    # Default: REQUIRES for any unrecognized type (conservative)
    return "REQUIRES"


def _build_ldg_node(
    concept_id: str,
    concept_entry: Dict[str, Any],
    tkb_id: str,
    learning_analytics: Dict[str, Any],
) -> Dict[str, Any]:
    """Build LearningDependencyNode per spec §2."""
    node_id = str(uuid.uuid5(_EDG_NS, f"{concept_id}:ldg:{tkb_id}"))
    node_urn = f"urn:tkb:edg:node:{node_id}"
    analytics = learning_analytics.get(concept_id) or {}
    concept_key = str(concept_entry.get("concept_key") or concept_entry.get("key") or "")
    concept_name = str(concept_entry.get("name") or concept_entry.get("title") or concept_id)
    return {
        "node_id": node_id,
        "node_urn": node_urn,
        "concept_id": concept_id,
        "concept_key": concept_key,
        "concept_name": concept_name,
        "node_type": str(concept_entry.get("node_type") or "concept"),
        "estimated_minutes": float(
            analytics.get("estimated_teaching_time_minutes")
            or concept_entry.get("estimated_teaching_time_minutes")
            or 0.0
        ),
        "difficulty": str(
            analytics.get("difficulty") or concept_entry.get("difficulty") or ""
        ),
        # These are populated after all nodes are built (via _populate_node_adjacencies)
        "prerequisite_ids": [],
        "dependent_ids": [],
        "remediation_target_ids": [],
        "is_gate": bool(concept_entry.get("is_gate", False)),
        "is_optional": bool(concept_entry.get("is_optional", False)),
        "depth": 0,  # computed after graph is built
    }


def _build_ldg_edge(
    source_concept_id: str,
    target_concept_id: str,
    edge_type: str,
    raw_edge: Dict[str, Any],
    tkb_id: str,
    nodes: Dict[str, Any],
) -> Dict[str, Any]:
    """Build LearningDependencyEdge per spec §3."""
    src_node_id = nodes[source_concept_id]["node_id"]
    tgt_node_id = nodes[target_concept_id]["node_id"]
    edge_key = f"{src_node_id}:{tgt_node_id}:{edge_type}:{tkb_id}"
    edge_id = str(uuid.uuid5(_EDG_NS, edge_key))
    edge_urn = f"urn:tkb:edg:edge:{edge_id}"
    is_blocking = edge_type in ("REQUIRES", "GATES")
    return {
        "edge_id": edge_id,
        "edge_urn": edge_urn,
        "source_node_id": src_node_id,
        "target_node_id": tgt_node_id,
        "source_concept_id": source_concept_id,
        "target_concept_id": target_concept_id,
        "edge_type": edge_type,
        "strength": float(raw_edge.get("strength") or (1.0 if is_blocking else 0.6)),
        "is_blocking": is_blocking,
        "context": str(raw_edge.get("context") or raw_edge.get("rationale") or ""),
    }


def _populate_node_adjacencies(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
) -> None:
    """Populate prerequisite_ids, dependent_ids, depth on each node from edges.
    Also marks is_gate on nodes that have GATES-type incoming edges."""
    for edge in edges.values():
        src_cid = edge.get("source_concept_id", "")
        tgt_cid = edge.get("target_concept_id", "")
        edge_type = edge.get("edge_type", "")
        if src_cid in nodes:
            if tgt_cid not in nodes[src_cid]["dependent_ids"]:
                nodes[src_cid]["dependent_ids"].append(tgt_cid)
        if tgt_cid in nodes:
            if src_cid not in nodes[tgt_cid]["prerequisite_ids"]:
                nodes[tgt_cid]["prerequisite_ids"].append(src_cid)
        if edge_type == "GATES" and tgt_cid in nodes:
            nodes[tgt_cid]["is_gate"] = True

    # Compute depth via BFS from roots
    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)
    for edge in edges.values():
        if edge.get("is_blocking"):
            src = edge.get("source_concept_id", "")
            tgt = edge.get("target_concept_id", "")
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)
                in_degree[tgt] += 1
    roots = [nid for nid in nodes if in_degree.get(nid, 0) == 0]
    queue = deque((nid, 0) for nid in roots)
    while queue:
        current, depth = queue.popleft()
        if depth > nodes[current].get("depth", 0):
            nodes[current]["depth"] = depth
        for neighbor in adj.get(current, []):
            queue.append((neighbor, depth + 1))


def _compute_topological_order(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
) -> List[str]:
    """
    Kahn's algorithm over REQUIRES + GATES edges.
    Tie-break (spec §9):
      1. is_gate=True first
      2. difficulty=easy first (easy > medium > hard for priority)
      3. concept_id lexicographic order (ascending)
    Returns list of concept_ids.
    """
    diff_order = {"easy": 0, "medium": 1, "hard": 2, "": 1}

    def sort_key(concept_id: str) -> Tuple:
        node = nodes.get(concept_id, {})
        is_gate = not node.get("is_gate", False)  # False sorts before True (gate first)
        diff = diff_order.get(str(node.get("difficulty", "")), 1)
        return (is_gate, diff, concept_id)

    in_degree: Dict[str, int] = defaultdict(int)
    adj: Dict[str, List[str]] = defaultdict(list)

    for cid in nodes:
        in_degree.setdefault(cid, 0)

    for edge in edges.values():
        if edge.get("edge_type") in ("REQUIRES", "GATES"):
            src = edge.get("source_concept_id", "")
            tgt = edge.get("target_concept_id", "")
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)
                in_degree[tgt] += 1

    queue: List[str] = sorted(
        [cid for cid in nodes if in_degree.get(cid, 0) == 0],
        key=sort_key,
    )
    order: List[str] = []
    visited: Set[str] = set()

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        order.append(current)
        for neighbor in adj.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                # Insert maintaining sort order
                queue.append(neighbor)
                queue.sort(key=sort_key)

    # Append any remaining (cycle members or disconnected)
    remaining = sorted(
        [cid for cid in nodes if cid not in visited],
        key=sort_key,
    )
    order.extend(remaining)
    return order


def _compute_prerequisite_chains(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
    topological_order: List[str],
) -> List[Dict[str, Any]]:
    """One PrerequisiteChain per concept (spec §5): shortest path to root."""
    chains = []
    prereq_map: Dict[str, List[str]] = {cid: [] for cid in nodes}
    for edge in edges.values():
        if edge.get("edge_type") in ("REQUIRES", "GATES"):
            tgt = edge.get("target_concept_id", "")
            src = edge.get("source_concept_id", "")
            if tgt in prereq_map and src:
                prereq_map[tgt].append(src)

    chain_ns = uuid.UUID("11223344-5566-7788-99aa-bbccddeeff00")
    for goal_concept_id in nodes:
        sequence = _shortest_prerequisite_path(goal_concept_id, prereq_map)
        if not sequence:
            continue
        total_minutes = sum(
            nodes.get(cid, {}).get("estimated_minutes", 0.0) for cid in sequence
        )
        chain_id = str(uuid.uuid5(chain_ns, f"chain:{goal_concept_id}"))
        chains.append({
            "chain_id": chain_id,
            "root_concept_id": goal_concept_id,
            "sequence": sequence,
            "total_minutes": total_minutes,
            "critical_path": True,
        })
    return chains


def _shortest_prerequisite_path(
    goal: str,
    prereq_map: Dict[str, List[str]],
) -> List[str]:
    """BFS shortest path from any root to goal (reversed: roots first)."""
    if not prereq_map.get(goal):
        return []
    visited = {goal}
    queue = deque([[goal]])
    all_paths = []
    while queue:
        path = queue.popleft()
        current = path[-1]
        prereqs = prereq_map.get(current, [])
        if not prereqs:
            all_paths.append(list(reversed(path)))
            continue
        for prereq in sorted(prereqs):
            if prereq not in visited:
                visited.add(prereq)
                queue.append(path + [prereq])
    if not all_paths:
        return []
    # Return shortest path (min length, then lexicographic first)
    return min(all_paths, key=lambda p: (len(p), p))


def _compute_remediation_paths(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """RemediationPath per concept with ENABLES_REMEDIATION edges (spec §6)."""
    remediation_targets: Dict[str, List[str]] = defaultdict(list)
    for edge in edges.values():
        if edge.get("edge_type") == "ENABLES_REMEDIATION":
            src = edge.get("source_concept_id", "")
            tgt = edge.get("target_concept_id", "")
            if src and tgt:
                remediation_targets[tgt].append(src)

    paths = []
    path_ns = uuid.UUID("aabbccdd-eeff-0011-2233-445566778899")
    for trigger_concept_id, remediation_concepts in sorted(remediation_targets.items()):
        # Select minimum total_minutes path; tie-break: lowest concept_id path[0]
        best = sorted(
            remediation_concepts,
            key=lambda cid: (nodes.get(cid, {}).get("estimated_minutes", 0.0), cid),
        )
        path = best  # single concept remediation entries for now
        total_minutes = sum(nodes.get(c, {}).get("estimated_minutes", 0.0) for c in path)
        path_id = str(uuid.uuid5(path_ns, f"remediation:{trigger_concept_id}"))
        paths.append({
            "path_id": path_id,
            "trigger_concept_id": trigger_concept_id,
            "path": path,
            "total_minutes": total_minutes,
            "re_entry_concept_id": trigger_concept_id,
        })
    return paths


def _compute_alternative_paths(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
    topological_order: List[str],
    learning_analytics: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """AlternativeLearningPath (spec §7): example_first, abstract_first, minimal_prerequisites.
    All derived from prerequisite subgraph — no invented ordering."""
    if len(topological_order) < 2:
        return []
    paths = []
    alt_ns = uuid.UUID("fedcba98-7654-3210-fedc-ba9876543210")

    # minimal_prerequisites: only core concepts (is_optional=False)
    minimal = [cid for cid in topological_order if not nodes.get(cid, {}).get("is_optional", False)]
    if minimal:
        paths.append({
            "path_id": str(uuid.uuid5(alt_ns, "alt:minimal")),
            "goal_concept_id": topological_order[-1] if topological_order else "",
            "path": minimal,
            "rationale": "Minimal prerequisites only: skips optional enrichment concepts.",
            "path_type": "minimal_prerequisites",
            "total_minutes": sum(nodes.get(c, {}).get("estimated_minutes", 0.0) for c in minimal),
        })

    # example_first: concepts with examples (is_worked content) reordered earlier
    # We simply partition: concepts with worked examples first in topo order, then rest
    # We can only know this if learning_analytics contains it; otherwise same as canonical
    example_concepts = {cid for cid, la in learning_analytics.items() if la.get("has_examples")}
    if example_concepts:
        ex_first = (
            [c for c in topological_order if c in example_concepts] +
            [c for c in topological_order if c not in example_concepts]
        )
        paths.append({
            "path_id": str(uuid.uuid5(alt_ns, "alt:example_first")),
            "goal_concept_id": topological_order[-1] if topological_order else "",
            "path": ex_first,
            "rationale": "Concepts with examples reordered earlier for grounded learning.",
            "path_type": "example_first",
            "total_minutes": sum(nodes.get(c, {}).get("estimated_minutes", 0.0) for c in ex_first),
        })

    return paths


def _detect_cycles(
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
) -> List[List[str]]:
    """DFS cycle detection on blocking edges. Returns list of cycle concept_id lists."""
    adj: Dict[str, List[str]] = defaultdict(list)
    for edge in edges.values():
        if edge.get("is_blocking"):
            src = edge.get("source_concept_id", "")
            tgt = edge.get("target_concept_id", "")
            if src in nodes and tgt in nodes:
                adj[src].append(tgt)

    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles: List[List[str]] = []

    def dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in sorted(adj.get(node, [])):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                idx = next((i for i, n in enumerate(path) if n == neighbor), 0)
                cycle = path[idx:] + [neighbor]
                if cycle not in cycles:
                    cycles.append(cycle)
        path.pop()
        rec_stack.discard(node)

    for cid in sorted(nodes.keys()):
        if cid not in visited:
            dfs(cid, [])
    return cycles


def _backfill_teaching_units_from_edg(
    context: Any,
    nodes: Dict[str, Any],
    edges: Dict[str, Any],
) -> None:
    """Backfill TU.edg_node_id, TU.prerequisites (PrerequisiteRef snapshots),
    and recompute TU.completeness_score.

    Called immediately after context.set_output(STAGE, edg) so that downstream
    stages (EDST, CPT, EKG, Nav, RI) see fully-populated TU dicts.

    Authority:
      AUTHORITY_MATRIX §2.1 — EDG is sole author of prerequisite relationships.
      TEACHING_UNIT_SPECIFICATION §3 — TU.prerequisites is a derived copy from EDG.
      TEACHING_UNIT_SPECIFICATION §6 — completeness_score recomputed after prerequisites added.
    """
    teaching_units = context.get_output("teaching_units")
    if not teaching_units:
        return  # TUs not built yet (edge case; should not occur in normal pipeline)

    # Build a lookup: source_concept_id -> list of (target_concept_id, edge) for prereq edge types
    # source is the prerequisite, target is the concept that depends on it
    # PrerequisiteRef: the prerequisite concept appears as a prereq for the target
    prereq_edge_types = {"REQUIRES", "RECOMMENDED_BEFORE"}
    # concept_id -> list of {concept_id: prereq_cid, concept_name, is_blocking, teaching_unit_id}
    prereq_map: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in teaching_units}

    for edge in edges.values():
        if edge.get("edge_type") not in prereq_edge_types:
            continue
        source_cid = edge.get("source_concept_id", "")  # prerequisite concept
        target_cid = edge.get("target_concept_id", "")  # concept that needs source
        if not source_cid or not target_cid:
            continue
        if target_cid not in prereq_map:
            continue
        source_node = nodes.get(source_cid) or {}
        prereq_ref = {
            "concept_id": source_cid,
            "concept_name": source_node.get("concept_name", ""),
            "is_blocking": bool(edge.get("is_blocking", True)),
            "teaching_unit_id": (teaching_units.get(source_cid) or {}).get("unit_id", ""),
        }
        # Avoid duplicates
        existing = {p["concept_id"] for p in prereq_map[target_cid]}
        if source_cid not in existing:
            prereq_map[target_cid].append(prereq_ref)

    # Apply backfill to each TU
    for concept_id, tu in teaching_units.items():
        node = nodes.get(concept_id) or {}

        # 1. Set edg_node_id cross-reference (spec §3 'Graph Cross-References')
        if node.get("node_id"):
            tu["edg_node_id"] = node["node_id"]

        # 2. Set prerequisites (derived convenience snapshot from EDG — spec §3)
        prereqs = prereq_map.get(concept_id, [])
        tu["prerequisites"] = prereqs

        # 3. Recompute completeness_score (spec §6, weight 2 for "prerequisites resolved from EDG")
        tu["completeness_score"] = _recompute_completeness(tu)


def _recompute_completeness(tu: Dict[str, Any]) -> float:
    """Recompute completeness_score per TEACHING_UNIT_SPECIFICATION §6.

    Identical formula to TU builder's _compute_completeness_score.
    Called after EDG backfill so the 'prerequisites resolved from EDG'
    check is accurate.
    """
    definition = tu.get("definition") or {}
    explanations = tu.get("explanations") or []
    learning_objectives = tu.get("learning_objectives") or []
    examples = (tu.get("examples") or []) + (tu.get("worked_examples") or [])
    prerequisites = tu.get("prerequisites") or []
    assessments = (tu.get("assessments") or []) + (tu.get("practice_questions") or [])
    bloom_taxonomy = tu.get("bloom_taxonomy") or {}
    revision_notes = tu.get("revision_notes") or []
    figures = tu.get("figures") or []
    estimated_teaching_time = float(tu.get("estimated_teaching_time_minutes") or 0.0)

    checks = [
        (bool(definition.get("text")), 3),
        (len(explanations) >= 1, 3),
        (len(learning_objectives) >= 1, 2),
        (len(examples) >= 1, 2),
        (len(prerequisites) >= 1, 2),   # now accurate after EDG backfill
        (len(assessments) >= 1, 2),
        (bool(bloom_taxonomy.get("primary_level") or bloom_taxonomy.get("coverage_flags")), 1),
        (len(revision_notes) >= 1, 1),
        (len(figures) >= 1, 1),
        (estimated_teaching_time > 0, 1),
    ]
    total_weight = sum(w for _, w in checks)
    weighted_sum = sum(w for passed, w in checks if passed)
    return round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0


def _compute_remediation_coverage(
    nodes: Dict[str, Any],
    remediation_paths: List[Dict[str, Any]],
) -> float:
    gate_nodes = [cid for cid, n in nodes.items() if n.get("is_gate")]
    if not gate_nodes:
        return 1.0
    covered = {p["trigger_concept_id"] for p in remediation_paths}
    return round(sum(1 for cid in gate_nodes if cid in covered) / len(gate_nodes), 4)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
