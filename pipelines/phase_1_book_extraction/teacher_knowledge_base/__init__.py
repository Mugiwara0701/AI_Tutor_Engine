"""
teacher_knowledge_base/ — M6.1: Teacher Knowledge Base Foundation & Core Builder.

MILESTONE: M6.1
STATUS: Implemented

This package implements the complete Teacher Knowledge Base build pipeline
as specified in:
  - M6_ARCHITECTURE_SPECIFICATION.md
  - TEACHER_KNOWLEDGE_BASE_SCHEMA.md
  - AUTHORITY_MATRIX.md
  - ENRICHED_DST_SPECIFICATION.md
  - ENRICHED_KNOWLEDGE_GRAPH_SPECIFICATION.md
  - ENRICHED_DEPENDENCY_GRAPH_SPECIFICATION.md
  - LEARNING_GRAPH_SPECIFICATION.md (concept_progression_templates)
  - CURRICULUM_GRAPH_SPECIFICATION.md
  - TEACHING_UNIT_SPECIFICATION.md
  - NAVIGATION_SYSTEM_SPECIFICATION.md
  - RUNTIME_API_SPECIFICATION.md

ARCHITECTURE: frozen. This milestone is implementation only. No architecture
was redesigned or modified.

PUBLIC API
----------
The primary external entry point for the TKB build:

    from teacher_knowledge_base.builder import build_teacher_knowledge_base
    result = build_teacher_knowledge_base(build=build, storage=storage)

    # Access the artifact
    artifact = result.artifact
    print(artifact.get_artifact_id())
    print(artifact.get_teaching_unit_count())

    # Persist to JSON
    from teacher_knowledge_base.serialization import artifact_to_json
    json_str = artifact_to_json(artifact)

PACKAGE STRUCTURE
-----------------
  builder.py        — public API (build_teacher_knowledge_base)
  engine.py         — pipeline orchestrator
  pipeline.py       — stage definitions and ordering
  context.py        — TKBContext (shared mutable build state)
  artifact.py       — TeacherKnowledgeBase dataclass + build_artifact()
  metadata.py       — TKBMetadata + TKBCompilerInformation
  loaders.py        — compiler artifact loaders
  statistics.py     — statistics computation
  validation.py     — validation passes (9 validators)
  serialization.py  — deterministic serialization + fingerprinting
  state.py          — module-level TKB state
  registry.py       — artifact manager integration
  exceptions.py     — exception hierarchy
  builders/
    edst_builder.py           — Enriched DST
    edg_builder.py            — Enriched Dependency Graph
    ekg_builder.py            — Enriched Knowledge Graph
    teaching_unit_builder.py  — Teaching Units
    progression_builder.py    — Concept Progression Templates
    curriculum_builder.py     — Curriculum Graph
    navigation_builder.py     — Navigation System
    runtime_index_builder.py  — Runtime Indexes

INTEGRATION
-----------
Reads from (existing, unmodified):
  artifact_manager.state    (get_current_build)
  build_metadata.state      (get_current_build_metadata)
  cache.state               (get_current_cache_entry)
  change_detection.state    (get_current_change_detection_report)
  canonicalization          (canonical_json, sha256_hexdigest, strip_volatile)

Writes to (new):
  teacher_knowledge_base.state

BACKWARD COMPATIBILITY
----------------------
No previous milestone module was modified. All integration is read-only
from existing state modules using already-public accessors.

DETERMINISM
-----------
  - All artifact IDs: UUID5 (content-derived, never random)
  - All list ordering: stable (sorted by content keys)
  - All serialization: canonical_json() + sort_keys=True
  - Fingerprinting: sha256_hexdigest(canonical_json(strip_volatile(artifact_dict)))
  - Identical input always produces identical output
"""

from .builder import build_teacher_knowledge_base, get_current_build_result
from .artifact import TeacherKnowledgeBase
from .exceptions import (
    TeacherKnowledgeBaseError,
    TKBBuildError,
    TKBValidationError,
    TKBSerializationError,
    TKBRegistrationError,
    TKBLoaderError,
    TKBBuilderError,
    TKBAmbiguityError,
)
from .state import (
    get_current_tkb_result,
    has_current_tkb_result,
    reset_all_tkb_state,
)

__all__ = [
    # Primary API
    "build_teacher_knowledge_base",
    "get_current_build_result",
    # Artifact class
    "TeacherKnowledgeBase",
    # Exceptions
    "TeacherKnowledgeBaseError",
    "TKBBuildError",
    "TKBValidationError",
    "TKBSerializationError",
    "TKBRegistrationError",
    "TKBLoaderError",
    "TKBBuilderError",
    "TKBAmbiguityError",
    # State
    "get_current_tkb_result",
    "has_current_tkb_result",
    "reset_all_tkb_state",
]
