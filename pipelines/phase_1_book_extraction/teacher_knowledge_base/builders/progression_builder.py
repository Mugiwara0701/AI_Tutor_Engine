"""
teacher_knowledge_base/builders/progression_builder.py — M6.1: Concept
Progression Template builder.

SPECIFICATION: LEARNING_GRAPH_SPECIFICATION.md (concept_progression_templates section)

SCOPE: ConceptProgressionTemplates define reusable teaching arc patterns for
concept sequences. Each template describes a canonical progression from
foundational to advanced concepts within a coherent subject cluster.

A progression template is NOT a concrete lesson plan — it is a pattern
template that Phase 2 runtime uses to instantiate adaptive teaching paths.
This builder ONLY produces the templates; runtime instantiation is Phase 2.

TEMPLATE STRUCTURE (per spec):
  - template_id (UUID5, deterministic)
  - template_name
  - progression_type: linear | branching | spiral | mastery
  - anchor_concept_id (the central concept this template is built around)
  - entry_concepts (prerequisites from outside this cluster)
  - core_sequence (ordered list of concept IDs — the main teaching arc)
  - exit_concepts (concepts this cluster enables downstream)
  - bloom_arc (Bloom level progression across the template)
  - difficulty_arc (easy -> medium -> hard progression)
  - estimated_total_duration_minutes
  - teaching_unit_ids (which TeachingUnits implement this template)

INPUT: EKG (concept clusters + learning paths), TeachingUnits.
"""
from __future__ import annotations

import json
import uuid
import logging
from typing import Any, Dict, List, Optional, Set

from ..exceptions import TKBBuilderError

logger = logging.getLogger("teacher_knowledge_base.builders.progression")

CPT_VERSION = "M6.1.0"
_CPT_NAMESPACE = uuid.UUID("11223344-5566-7788-99aa-bbccddeeff00")

STAGE = "concept_progression_templates"

_BLOOM_ORDER = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


def build(context: "TKBContext") -> None:  # noqa: F821
    import time
    t0 = time.monotonic()
    try:
        _build_progression_templates(context)
    except TKBBuilderError:
        raise
    except Exception as exc:
        raise TKBBuilderError(STAGE, str(exc)) from exc
    finally:
        context.record_stage_timing(STAGE, time.monotonic() - t0)


def _build_progression_templates(context: "TKBContext") -> None:
    ekg = context.require_output("ekg", STAGE)
    teaching_units = context.require_output("teaching_units", STAGE)

    concept_clusters = ekg.get("concept_clusters") or []
    learning_paths = ekg.get("learning_paths") or []
    ekg_nodes = ekg.get("nodes") or []
    artifact_id = context.metadata.artifact_id

    # Build per-cluster node lookup
    node_lookup: Dict[str, Dict[str, Any]] = {}
    for n in ekg_nodes:
        nid = str(n.get("id") or n.get("concept_id") or n.get("enriched_id", ""))
        if nid:
            node_lookup[nid] = n

    # Build unit lookup: unit_id -> unit
    unit_lookup: Dict[str, Dict[str, Any]] = {u["unit_id"]: u for u in teaching_units}

    templates: List[Dict[str, Any]] = []

    # One template per concept cluster
    for cluster in concept_clusters:
        template = _build_cluster_template(
            cluster=cluster,
            node_lookup=node_lookup,
            unit_lookup=unit_lookup,
            artifact_id=artifact_id,
        )
        if template:
            templates.append(template)

    # Additional template from learning paths (if any)
    for lp in learning_paths:
        template = _build_path_template(
            learning_path=lp,
            node_lookup=node_lookup,
            unit_lookup=unit_lookup,
            artifact_id=artifact_id,
        )
        if template:
            templates.append(template)

    # Deduplicate by template_id, stable sort
    seen: Set[str] = set()
    unique_templates = []
    for t in sorted(templates, key=lambda x: x.get("template_id", "")):
        tid = t.get("template_id", "")
        if tid not in seen:
            seen.add(tid)
            unique_templates.append(t)

    context.set_output(STAGE, unique_templates)
    logger.info(
        "Progression Template builder: produced %d concept progression templates.",
        len(unique_templates),
    )


def _build_cluster_template(
    cluster: Dict[str, Any],
    node_lookup: Dict[str, Dict[str, Any]],
    unit_lookup: Dict[str, Dict[str, Any]],
    artifact_id: str,
) -> Optional[Dict[str, Any]]:
    concept_ids = cluster.get("concept_ids") or []
    if not concept_ids:
        return None

    cluster_key = str(cluster.get("cluster_key") or cluster.get("cluster_id") or "")
    key = json.dumps(
        {"cluster_key": cluster_key, "concepts": sorted(concept_ids)},
        sort_keys=True, separators=(",", ":"),
    )
    template_id = str(uuid.uuid5(_CPT_NAMESPACE, f"{artifact_id}:cpt:cluster:{key}"))

    # Sort concepts by prerequisite weight (descending = anchor first)
    ordered = _order_concepts_for_teaching(concept_ids, node_lookup)
    core_sequence = [str(c) for c in ordered]
    anchor = core_sequence[0] if core_sequence else ""

    # Entry/exit concepts
    entry_concepts = _compute_entry_concepts(concept_ids, node_lookup)
    exit_concepts = _compute_exit_concepts(concept_ids, node_lookup)

    bloom_arc = _compute_bloom_arc(ordered, node_lookup)
    difficulty_arc = _compute_difficulty_arc(ordered, node_lookup)
    total_duration = _compute_total_duration(concept_ids, node_lookup)
    progression_type = _classify_progression_type(bloom_arc, difficulty_arc)

    # Find TeachingUnits that implement this cluster
    implementing_units = [
        uid for uid, u in unit_lookup.items()
        if any(cid in concept_ids for cid in u.get("concepts", []))
    ]

    anchor_node = node_lookup.get(anchor) or {}
    return {
        "template_id": template_id,
        "version": CPT_VERSION,
        "template_name": f"Progression: {anchor_node.get('name') or anchor or cluster_key}",
        "cluster_key": cluster_key,
        "progression_type": progression_type,
        "anchor_concept_id": anchor,
        "entry_concepts": entry_concepts,
        "core_sequence": core_sequence,
        "exit_concepts": exit_concepts,
        "bloom_arc": bloom_arc,
        "difficulty_arc": difficulty_arc,
        "estimated_total_duration_minutes": max(10, total_duration),
        "teaching_unit_ids": sorted(implementing_units),
        "concept_count": len(concept_ids),
    }


def _build_path_template(
    learning_path: Dict[str, Any],
    node_lookup: Dict[str, Dict[str, Any]],
    unit_lookup: Dict[str, Dict[str, Any]],
    artifact_id: str,
) -> Optional[Dict[str, Any]]:
    concept_sequence = learning_path.get("concept_sequence") or []
    if not concept_sequence:
        return None

    path_id = str(learning_path.get("path_id") or "")
    key = json.dumps({"path_id": path_id, "sequence": concept_sequence},
                     sort_keys=True, separators=(",", ":"))
    template_id = str(uuid.uuid5(_CPT_NAMESPACE, f"{artifact_id}:cpt:path:{key}"))

    bloom_arc = _compute_bloom_arc(concept_sequence, node_lookup)
    difficulty_arc = _compute_difficulty_arc(concept_sequence, node_lookup)
    total_duration = _compute_total_duration(concept_sequence, node_lookup)
    anchor = concept_sequence[0] if concept_sequence else ""
    anchor_node = node_lookup.get(anchor) or {}

    implementing_units = [
        uid for uid, u in unit_lookup.items()
        if any(cid in concept_sequence for cid in u.get("concepts", []))
    ]

    return {
        "template_id": template_id,
        "version": CPT_VERSION,
        "template_name": f"Learning Path: {anchor_node.get('name') or anchor}",
        "cluster_key": f"path:{path_id}",
        "progression_type": "linear",
        "anchor_concept_id": anchor,
        "entry_concepts": [],
        "core_sequence": list(concept_sequence),
        "exit_concepts": [],
        "bloom_arc": bloom_arc,
        "difficulty_arc": difficulty_arc,
        "estimated_total_duration_minutes": max(10, total_duration),
        "teaching_unit_ids": sorted(implementing_units),
        "concept_count": len(concept_sequence),
    }


def _order_concepts_for_teaching(
    concept_ids: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Orders concepts: higher prerequisite_ordering_weight first (anchor concepts first),
    then alphabetically."""
    def sort_key(cid: str):
        n = node_lookup.get(str(cid)) or {}
        weight = n.get("pedagogical_metadata", {}).get("prerequisite_ordering_weight", 1.0)
        return (-float(weight), str(cid))
    return sorted(concept_ids, key=sort_key)


def _compute_entry_concepts(
    concept_ids: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Concepts that are prerequisites FROM OUTSIDE this cluster."""
    cluster_set = set(concept_ids)
    entry: Set[str] = set()
    for cid in concept_ids:
        n = node_lookup.get(str(cid)) or {}
        for prereq in (n.get("prerequisites") or
                       n.get("pedagogical_metadata", {}).get("prerequisite_concept_ids") or []):
            prereq_str = str(prereq)
            if prereq_str not in cluster_set:
                entry.add(prereq_str)
    return sorted(entry)


def _compute_exit_concepts(
    concept_ids: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Concepts enabled by this cluster that are outside the cluster."""
    cluster_set = set(concept_ids)
    exits: Set[str] = set()
    for cid in concept_ids:
        n = node_lookup.get(str(cid)) or {}
        for dep in (n.get("dependents") or n.get("enables") or []):
            dep_str = str(dep)
            if dep_str not in cluster_set:
                exits.add(dep_str)
    return sorted(exits)


def _compute_bloom_arc(
    sequence: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    arc = []
    for cid in sequence:
        n = node_lookup.get(str(cid)) or {}
        bl = n.get("pedagogical_metadata", {}).get("bloom_taxonomy_level", "understand")
        if not arc or arc[-1] != bl:
            arc.append(bl)
    return arc


def _compute_difficulty_arc(
    sequence: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    arc = []
    for cid in sequence:
        n = node_lookup.get(str(cid)) or {}
        d = n.get("pedagogical_metadata", {}).get("difficulty_level", "medium")
        if not arc or arc[-1] != d:
            arc.append(d)
    return arc


def _compute_total_duration(
    concept_ids: List[str],
    node_lookup: Dict[str, Dict[str, Any]],
) -> int:
    total = 0
    for cid in concept_ids:
        n = node_lookup.get(str(cid)) or {}
        total += n.get("pedagogical_metadata", {}).get("estimated_mastery_time_minutes", 30)
    return total


def _classify_progression_type(bloom_arc: List[str], difficulty_arc: List[str]) -> str:
    """Classifies the progression pattern type."""
    if len(bloom_arc) >= 4:
        return "spiral"
    if len(set(difficulty_arc)) == 1:
        return "mastery"
    if len(bloom_arc) == 1:
        return "linear"
    return "branching"
