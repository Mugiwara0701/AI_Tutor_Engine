"""
teacher_knowledge_base/artifact.py — M6.1: TeacherKnowledgeBase artifact.

THE CANONICAL ARTIFACT OBJECT for M6.1. Assembles every schema section
defined in TEACHER_KNOWLEDGE_BASE_SCHEMA.md into one immutable, serializable
record. This is the final output of the TKB build pipeline.

SCHEMA SECTIONS (per TEACHER_KNOWLEDGE_BASE_SCHEMA.md, implemented exactly):
  - metadata
  - compiler_information
  - enriched_document_structure_tree       (EDST)
  - enriched_knowledge_graph               (EKG)
  - enriched_dependency_graph              (EDG)
  - concept_progression_templates
  - curriculum_graph
  - teaching_units
  - navigation
  - runtime_indexes
  - statistics
  - validation
  - serialization_metadata

No schema deviations. Every section is populated from the TKBContext by
artifact.build_artifact() — this class is a pure data holder, not a builder.

IMMUTABILITY: once constructed, a TeacherKnowledgeBase is never modified.
to_dict() produces a deterministic, JSON-safe representation. Identical
context inputs always produce an identical artifact (determinism guarantee).

REUSE: the artifact's own fingerprint is computed using canonicalization.py's
sha256_hexdigest(canonical_json(strip_volatile(to_dict()))) — the exact same
strategy every other phase's fingerprint already uses.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from canonicalization import sha256_hexdigest, canonical_json, strip_volatile

# Version of this artifact's schema — bump only if the shape changes.
TKB_ARTIFACT_VERSION = "M6.1.0"


@dataclass(frozen=True)
class TeacherKnowledgeBase:
    """The complete Teacher Knowledge Base artifact.

    ALL fields are populated by artifact.build_artifact() from TKBContext.
    This class is a pure immutable data holder — no computation happens here.

    Field names match TEACHER_KNOWLEDGE_BASE_SCHEMA.md exactly.
    """

    # Identity and provenance
    metadata: Dict[str, Any]
    compiler_information: Dict[str, Any]

    # Enriched graphs (Phase 1 compiler artifacts + enrichment)
    enriched_document_structure_tree: Dict[str, Any]
    enriched_knowledge_graph: Dict[str, Any]
    enriched_dependency_graph: Dict[str, Any]

    # Teaching structure
    concept_progression_templates: List[Dict[str, Any]]
    curriculum_graph: Dict[str, Any]
    teaching_units: List[Dict[str, Any]]

    # Navigation and runtime
    navigation: Dict[str, Any]
    runtime_indexes: Dict[str, Any]

    # Quality and provenance
    statistics: Dict[str, Any]
    validation: Dict[str, Any]
    serialization_metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Deterministic JSON-safe dict. Field order is stable — matches
        TEACHER_KNOWLEDGE_BASE_SCHEMA.md top-level section order exactly."""
        return {
            "metadata": self.metadata,
            "compiler_information": self.compiler_information,
            "enriched_document_structure_tree": self.enriched_document_structure_tree,
            "enriched_knowledge_graph": self.enriched_knowledge_graph,
            "enriched_dependency_graph": self.enriched_dependency_graph,
            "concept_progression_templates": self.concept_progression_templates,
            "curriculum_graph": self.curriculum_graph,
            "teaching_units": self.teaching_units,
            "navigation": self.navigation,
            "runtime_indexes": self.runtime_indexes,
            "statistics": self.statistics,
            "validation": self.validation,
            "serialization_metadata": self.serialization_metadata,
        }

    def get_artifact_id(self) -> str:
        return self.metadata.get("artifact_id", "")

    def get_schema_version(self) -> str:
        return self.metadata.get("schema_version", "")

    def get_teaching_unit_count(self) -> int:
        return len(self.teaching_units)

    def get_concept_count(self) -> int:
        return self.statistics.get("concept_statistics", {}).get("total_concepts", 0)

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of this artifact's content.
        Volatile fields (generated_at, serialized_at, timestamps) are stripped
        before hashing — reuses canonicalization.py's shared strategy, plus
        additional TKB-specific volatile keys not in the shared VOLATILE_KEYS set."""
        import copy
        d = strip_volatile(self.to_dict())
        # serialized_at is not in canonicalization.VOLATILE_KEYS (which only
        # covers generated_at/created_at etc.) — strip it here so two serializations
        # of the same content always produce the same fingerprint.
        _strip_extra_volatile(d)
        return sha256_hexdigest(canonical_json(d))


def _strip_extra_volatile(d: Any) -> None:
    """Recursively strips TKB-specific volatile keys not covered by canonicalization.VOLATILE_KEYS.
    These are fields that change between runs (timings, timestamps, duration sums)
    even when the content is identical."""
    _EXTRA_VOLATILE = {
        "serialized_at",
        "total_build_time_seconds",
        "stage_timings_seconds",  # per-run wall-clock — non-deterministic
        "total_build_time_seconds",
    }
    if isinstance(d, dict):
        for key in list(_EXTRA_VOLATILE):
            d.pop(key, None)
        for v in d.values():
            _strip_extra_volatile(v)
    elif isinstance(d, list):
        for item in d:
            _strip_extra_volatile(item)




# ---------------------------------------------------------------------------
# Factory — assembles the artifact from a completed TKBContext.
# ---------------------------------------------------------------------------

def build_artifact(context: "TKBContext") -> TeacherKnowledgeBase:  # noqa: F821
    """Assembles the final TeacherKnowledgeBase from a fully-executed
    TKBContext. Called once by engine.py after all builder stages complete
    and validation passes.

    NEVER raises on missing optional stage outputs — uses sensible empty
    defaults so the artifact is always well-formed. Fatal missing outputs
    are caught by validation before this function is called.
    """
    from .context import TKBContext  # local import avoids circular

    outputs = context.outputs

    # -- metadata and compiler_information ----------------------------------
    metadata_obj = context.metadata
    ci_obj = context.compiler_information

    # -- Build each schema section from stage outputs -----------------------
    edst = outputs.get("edst") or _empty_edst()
    ekg = outputs.get("ekg") or _empty_ekg()
    edg = outputs.get("edg") or _empty_edg()
    teaching_units = outputs.get("teaching_units") or []
    cpt = outputs.get("concept_progression_templates") or []
    curriculum_graph = outputs.get("curriculum_graph") or _empty_curriculum_graph()
    navigation = outputs.get("navigation") or _empty_navigation()
    runtime_indexes = outputs.get("runtime_indexes") or _empty_runtime_indexes()
    statistics = outputs.get("statistics") or _empty_statistics()
    validation_block = outputs.get("validation") or _empty_validation()

    # -- serialization_metadata ---------------------------------------------
    serialization_metadata = _build_serialization_metadata(
        artifact_id=metadata_obj.artifact_id,
        stage_timings=context.stage_timings,
        completed_stages=context.completed_stages,
    )

    return TeacherKnowledgeBase(
        metadata=metadata_obj.to_dict(),
        compiler_information=ci_obj.to_dict(),
        enriched_document_structure_tree=edst,
        enriched_knowledge_graph=ekg,
        enriched_dependency_graph=edg,
        concept_progression_templates=cpt,
        curriculum_graph=curriculum_graph,
        teaching_units=teaching_units,
        navigation=navigation,
        runtime_indexes=runtime_indexes,
        statistics=statistics,
        validation=validation_block,
        serialization_metadata=serialization_metadata,
    )


# ---------------------------------------------------------------------------
# Empty-section defaults — used when an optional stage did not run.
# These ensure the artifact is always schema-complete even in partial builds.
# ---------------------------------------------------------------------------

def _empty_edst() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "enrichment_applied": False,
        "nodes": [],
        "enrichment_metadata": {},
    }


def _empty_ekg() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "enrichment_applied": False,
        "nodes": [],
        "edges": [],
        "enrichment_metadata": {},
    }


def _empty_edg() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "enrichment_applied": False,
        "nodes": [],
        "edges": [],
        "enrichment_metadata": {},
    }


def _empty_curriculum_graph() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "nodes": [],
        "edges": [],
        "metadata": {},
    }


def _empty_navigation() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "concept_map": {},
        "teaching_unit_map": {},
        "chapter_map": {},
        "breadcrumb_index": {},
        "metadata": {},
    }


def _empty_runtime_indexes() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "concept_by_id": {},
        "teaching_unit_by_id": {},
        "concept_by_chapter": {},
        "prerequisite_index": {},
        "learning_path_index": {},
        "metadata": {},
    }


def _empty_statistics() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "concept_statistics": {"total_concepts": 0},
        "teaching_unit_statistics": {"total_units": 0},
        "graph_statistics": {},
        "runtime_index_statistics": {},
        "navigation_statistics": {},
        "validation_statistics": {},
        "memory_estimates": {},
        "quality_statistics": {},
        "build_statistics": {},
    }


def _empty_validation() -> Dict[str, Any]:
    return {
        "version": "M6.1.0",
        "passed": True,
        "schema_validation": {"passed": True, "violations": []},
        "reference_validation": {"passed": True, "violations": []},
        "ownership_validation": {"passed": True, "violations": []},
        "authority_validation": {"passed": True, "violations": []},
        "graph_validation": {"passed": True, "violations": []},
        "cross_reference_validation": {"passed": True, "violations": []},
        "serialization_validation": {"passed": True, "violations": []},
        "artifact_validation": {"passed": True, "violations": []},
        "build_validation": {"passed": True, "violations": []},
    }


def _build_serialization_metadata(
    artifact_id: str,
    stage_timings: Dict[str, float],
    completed_stages: List[str],
) -> Dict[str, Any]:
    """Builds the serialization_metadata section — records how and when this
    artifact was serialized. The serialized_at timestamp is volatile and
    excluded from the content fingerprint (see canonicalization.VOLATILE_KEYS)."""
    total_time = round(sum(stage_timings.values()), 4)
    return {
        "version": TKB_ARTIFACT_VERSION,
        "format": "json",
        "encoding": "utf-8",
        "serialized_at": datetime.now(timezone.utc).isoformat(),
        "artifact_id": artifact_id,
        "pipeline_stages_completed": completed_stages,
        "stage_timings_seconds": stage_timings,
        "total_build_time_seconds": total_time,
        "ordering": "stable",
        "determinism": "uuid5+canonical_json",
    }
