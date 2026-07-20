"""
teacher_knowledge_base/artifact.py — M6.1/M6.2 (remediated)

Assembles the final TeacherKnowledgeBase from TKBContext.
Schema exactly as defined in TEACHER_KNOWLEDGE_BASE_SCHEMA.md v1.1.1.

TOP-LEVEL FIELDS (spec §1):
  tkb_id, tkb_urn, tkb_version, schema_version,
  metadata (TKBMetadata), compiler_information (TKBCompilerInfo),
  enriched_document_structure_tree, enriched_knowledge_graph,
  enriched_dependency_graph,
  concept_progression_templates: Dict[concept_id -> CPT],
  curriculum_graph,
  teaching_units: Dict[concept_id -> TeachingUnit],
  navigation (NavigationIndex with 6 sub-navigations),
  runtime_indexes (RuntimeIndexes with 7 indexes),
  statistics (TKBStatistics),
  validation (TKBValidation),
  serialization_metadata (TKBSerializationMetadata)

IMMUTABLE: once constructed, never modified.
DETERMINISTIC: identical inputs -> identical output.

SERIALIZATION METADATA (spec §9):
  {format, schema_version, encoding, sort_keys,
   search_version="lexical_v1", embedding_model=null, created_at, content_hash, byte_size}
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonicalization import sha256_hexdigest, canonical_json, strip_volatile

from .metadata import TKBMetadata, TKBCompilerInfo, TKB_VERSION, TKB_SCHEMA_VERSION, make_tkb_urn

TKB_ARTIFACT_VERSION = TKB_VERSION  # "1.1.1"

# Extra volatile keys not in canonicalization.VOLATILE_KEYS
_EXTRA_VOLATILE = frozenset({
    "serialized_at", "created_at", "validated_at", "content_hash",
    "byte_size", "total_build_time_seconds", "stage_timings_seconds",
})


@dataclass(frozen=True)
class TeacherKnowledgeBase:
    """Immutable TeacherKnowledgeBase artifact per TEACHER_KNOWLEDGE_BASE_SCHEMA.md §1."""
    # --- Top-level identity (spec §1) ---
    tkb_id:         str
    tkb_urn:        str
    tkb_version:    str     # "1.1.1"
    schema_version: str     # "1.1.1"

    # --- Sections ---
    metadata:                          Dict[str, Any]   # TKBMetadata dict
    compiler_information:              Dict[str, Any]   # TKBCompilerInfo dict
    enriched_document_structure_tree:  Dict[str, Any]
    enriched_knowledge_graph:          Dict[str, Any]
    enriched_dependency_graph:         Dict[str, Any]
    concept_progression_templates:     Dict[str, Any]  # Dict[concept_id -> CPT]
    curriculum_graph:                  Dict[str, Any]
    teaching_units:                    Dict[str, Any]  # Dict[concept_id -> TeachingUnit]
    navigation:                        Dict[str, Any]  # NavigationIndex
    runtime_indexes:                   Dict[str, Any]  # RuntimeIndexes
    statistics:                        Dict[str, Any]  # TKBStatistics
    validation:                        Dict[str, Any]  # TKBValidation
    serialization_metadata:            Dict[str, Any]  # TKBSerializationMetadata

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic, JSON-safe dict. Field order matches spec §1 top-level ordering."""
        return {
            "tkb_id":           self.tkb_id,
            "tkb_urn":          self.tkb_urn,
            "tkb_version":      self.tkb_version,
            "schema_version":   self.schema_version,
            "metadata":         self.metadata,
            "compiler_information": self.compiler_information,
            "enriched_document_structure_tree": self.enriched_document_structure_tree,
            "enriched_knowledge_graph": self.enriched_knowledge_graph,
            "enriched_dependency_graph": self.enriched_dependency_graph,
            "concept_progression_templates": self.concept_progression_templates,
            "curriculum_graph": self.curriculum_graph,
            "teaching_units":   self.teaching_units,
            "navigation":       self.navigation,
            "runtime_indexes":  self.runtime_indexes,
            "statistics":       self.statistics,
            "validation":       self.validation,
            "serialization_metadata": self.serialization_metadata,
        }

    def fingerprint(self) -> str:
        """SHA-256 of the artifact content, excluding volatile fields.
        Same strategy as every other Phase in this codebase."""
        import copy
        d = strip_volatile(copy.deepcopy(self.to_dict()))
        _strip_extra_volatile_recursive(d)
        return sha256_hexdigest(canonical_json(d))

    def get_tkb_id(self) -> str:
        return self.tkb_id

    def get_schema_version(self) -> str:
        return self.schema_version

    def get_total_concepts(self) -> int:
        return len(self.teaching_units)

    def get_total_teaching_units(self) -> int:
        return len(self.teaching_units)


def _strip_extra_volatile_recursive(d: Any) -> None:
    """Strips extra volatile keys not covered by canonicalization.VOLATILE_KEYS."""
    if isinstance(d, dict):
        for key in list(d.keys()):
            if key in _EXTRA_VOLATILE:
                del d[key]
            else:
                _strip_extra_volatile_recursive(d[key])
    elif isinstance(d, list):
        for item in d:
            _strip_extra_volatile_recursive(item)


def build_artifact(context: "TKBContext") -> TeacherKnowledgeBase:  # noqa: F821
    """Assembles the final TeacherKnowledgeBase from a complete TKBContext.
    All required stage outputs must be present. Fatal missing outputs are
    caught by validation before this is called."""
    outputs = context.outputs
    metadata_obj = context.metadata
    ci_obj = context.compiler_information

    tkb_id = metadata_obj.tkb_id
    tkb_urn = make_tkb_urn(tkb_id)

    # Retrieve stage outputs (validated before assembly)
    edst = outputs.get("edst") or _empty_edst()
    edg = outputs.get("edg") or _empty_edg()
    ekg = outputs.get("ekg") or _empty_ekg()
    cpts = outputs.get("concept_progression_templates") or {}
    curriculum_graph = outputs.get("curriculum_graph") or _empty_curriculum_graph()
    teaching_units = outputs.get("teaching_units") or {}
    navigation = outputs.get("navigation") or _empty_navigation()
    runtime_indexes = outputs.get("runtime_indexes") or _empty_runtime_indexes()
    statistics = outputs.get("statistics") or _empty_statistics()
    validation_block = outputs.get("validation") or _empty_validation()

    # Serialization metadata (spec §9)
    serialization_metadata = _build_serialization_metadata(
        tkb_id=tkb_id,
        completed_stages=context.completed_stages,
        stage_timings=context.stage_timings,
    )

    return TeacherKnowledgeBase(
        tkb_id=tkb_id,
        tkb_urn=tkb_urn,
        tkb_version=TKB_VERSION,
        schema_version=TKB_SCHEMA_VERSION,
        metadata=metadata_obj.to_dict(),
        compiler_information=ci_obj.to_dict(),
        enriched_document_structure_tree=edst,
        enriched_knowledge_graph=ekg,
        enriched_dependency_graph=edg,
        concept_progression_templates=cpts,
        curriculum_graph=curriculum_graph,
        teaching_units=teaching_units,
        navigation=navigation,
        runtime_indexes=runtime_indexes,
        statistics=statistics,
        validation=validation_block,
        serialization_metadata=serialization_metadata,
    )


# ---------------------------------------------------------------------------
# Empty defaults — used when an optional stage did not run
# ---------------------------------------------------------------------------

def _empty_edst() -> Dict[str, Any]:
    return {"edst_id": "", "original_dst_id": "", "root_node_id": "", "nodes": {}, "node_count": 0, "max_depth": 0, "metadata": {}, "validation": {"status": "UNKNOWN", "warnings": []}}


def _empty_edg() -> Dict[str, Any]:
    return {"edg_id": "", "original_dep_graph_id": "", "nodes": {}, "edges": {}, "prerequisite_chains": [], "remediation_paths": [], "alternative_paths": [], "topological_order": [], "node_count": 0, "edge_count": 0, "metadata": {}, "validation": {"is_dag": True, "status": "UNKNOWN", "warnings": [], "errors": []}}


def _empty_ekg() -> Dict[str, Any]:
    return {"ekg_id": "", "original_kg_id": "", "nodes": {}, "edges": {}, "node_count": 0, "edge_count": 0, "metadata": {}, "validation": {"status": "UNKNOWN", "warnings": []}}


def _empty_curriculum_graph() -> Dict[str, Any]:
    return {"cg_id": "", "scope_description": "within-book v1", "nodes": {}, "edges": {}, "cross_chapter_links": [], "node_count": 0, "edge_count": 0, "scopes_present": [], "metadata": {}, "validation": {"status": "UNKNOWN", "warnings": []}}


def _empty_navigation() -> Dict[str, Any]:
    return {
        "teacher_navigation": {"nav_id": "", "ordered_sections": [], "concept_to_section": {}},
        "question_navigation": {"nav_id": "", "by_difficulty": {}, "by_bloom_level": {}, "by_concept": {}, "by_type": {}, "by_provenance_tier": {}, "chapter_test_item_ids": [], "quick_check_item_ids": []},
        "concept_navigation": {"nav_id": "", "concept_index": {}, "name_lookup": {}, "alias_lookup": {}},
        "revision_navigation": {"nav_id": "", "full_chapter_revision": [], "by_importance": {}, "key_formula_ids": [], "definition_concept_ids": [], "mnemonics_available": [], "revision_by_time": {}, "spaced_repetition_groups": []},
        "assessment_navigation": {"nav_id": "", "formative_sets": [], "summative_sets": [], "diagnostic_sets": [], "by_concept": {}},
        "learning_path_navigation": {"nav_id": "", "canonical_path": [], "beginner_path": [], "accelerated_path": [], "prerequisite_first_path": [], "example_first_path": [], "paths_by_time": {}},
    }


def _empty_runtime_indexes() -> Dict[str, Any]:
    return {
        "concept_lookup_index": {"by_id": {}, "by_key": {}, "by_name": {}},
        "semantic_search_index": {"entries": [], "total_entries": 0},
        "prerequisite_index": {"by_concept": {}},
        "teaching_retrieval_index": {"by_concept_id": {}, "by_section_id": {}, "by_difficulty": {}, "by_importance": {}},
        "revision_retrieval_index": {"by_concept_id": {}, "formula_ids_ordered": [], "definition_index": {}, "core_concept_ids": []},
        "assessment_retrieval_index": {"by_concept_id": {}, "by_difficulty": {}, "by_bloom_level": {}, "by_type": {}, "by_provenance_tier": {}, "chapter_test_item_ids": [], "assessment_item_location": {}},
        "curriculum_traversal_index": {"by_concept_id": {}, "cross_chapter": []},
    }


def _empty_statistics() -> Dict[str, Any]:
    return {
        "total_concepts": 0, "total_teaching_units": 0, "total_learning_objectives": 0,
        "total_assessments": 0, "total_practice_questions": 0, "total_prerequisites": 0,
        "total_ekg_edges": 0, "total_edg_edges": 0, "total_curriculum_links": 0,
        "total_figures": 0, "total_examples": 0, "total_formulae": 0,
        "total_worked_examples": 0, "total_activities": 0, "coverage_score": 0.0,
        "avg_completeness_score": 0.0, "avg_prerequisites_per_concept": 0.0,
        "estimated_total_teaching_time_minutes": 0.0, "assessment_coverage_rate": 0.0,
    }


def _empty_validation() -> Dict[str, Any]:
    return {
        "status": "VALID",
        "checks": [],
        "warnings": [],
        "errors": [],
        "validated_at": "",
    }


def _build_serialization_metadata(
    tkb_id: str,
    completed_stages: List[str],
    stage_timings: Dict[str, float],
) -> Dict[str, Any]:
    """TKBSerializationMetadata per spec §9. search_version='lexical_v1', embedding_model=null."""
    return {
        "format": "json",
        "schema_version": TKB_SCHEMA_VERSION,
        "encoding": "utf-8",
        "sort_keys": True,
        "search_version": "lexical_v1",   # spec §9 — no vectors in v1
        "embedding_model": None,           # null in v1 (spec §9)
        "created_at": datetime.now(timezone.utc).isoformat(),  # volatile, excluded from fingerprint
        "content_hash": "",                # computed post-assembly and injected
        "byte_size": 0,                    # computed post-serialization and injected
        # Internal build tracking (not in spec; removed from fingerprint)
        "pipeline_stages_completed": completed_stages,
        "stage_timings_seconds": stage_timings,
    }
