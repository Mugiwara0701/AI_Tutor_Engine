# Teacher Knowledge Base — M6.1

**Milestone:** M6.1 — Teacher Knowledge Base Foundation & Core Builder  
**Status:** ✅ Implemented  
**Architecture:** Frozen (per M6.0.3 Editorial Freeze)

---

## Overview

The `teacher_knowledge_base/` package implements the complete TKB build pipeline as specified in the frozen M6.0 architecture. It takes Phase 1 compiler artifacts as input and produces a deterministic `TeacherKnowledgeBase` artifact containing all enriched graphs, teaching structures, navigation indexes, and runtime lookup tables needed by the Phase 2 runtime.

**This is a build-time pipeline only.** Phase 2 runtime, StudentLearningState, PedagogyProfile, adaptive tutoring, and search are out of scope for M6.1.

---

## Architecture

```
OptimizedKnowledgePackage (Phase E5 cache)
MasterKnowledgePackage   (Phase B compiler)
KnowledgeGraph           (Phase C graph)
DocumentStructureTree    (Phase A DST)
SemanticGraph            (Phase C)
ChapterJSON              (per-chapter JSON)
CompilerReleaseManifest  (Phase D3 release)
         ↓
   TKB Builder Pipeline
         ↓
   TeacherKnowledgeBase
```

### Pipeline Stages (in order)

| Stage | Module | Output |
|-------|--------|--------|
| Enriched DST | `builders/edst_builder.py` | enriched_document_structure_tree |
| Enriched Dependency Graph | `builders/edg_builder.py` | enriched_dependency_graph |
| Enriched Knowledge Graph | `builders/ekg_builder.py` | enriched_knowledge_graph |
| Teaching Units | `builders/teaching_unit_builder.py` | teaching_units |
| Concept Progression Templates | `builders/progression_builder.py` | concept_progression_templates |
| Curriculum Graph | `builders/curriculum_builder.py` | curriculum_graph |
| Navigation System | `builders/navigation_builder.py` | navigation |
| Runtime Indexes | `builders/runtime_index_builder.py` | runtime_indexes |
| Statistics | `statistics.py` | statistics |
| Validation | `validation.py` | validation |

---

## Module Responsibilities

| Module | Role |
|--------|------|
| `builder.py` | Public API — `build_teacher_knowledge_base()` |
| `engine.py` | Pipeline orchestrator — runs stages in order |
| `pipeline.py` | Stage definitions and ordering |
| `context.py` | `TKBContext` — shared mutable build state passed through all stages |
| `artifact.py` | `TeacherKnowledgeBase` dataclass + `build_artifact()` |
| `metadata.py` | `TKBMetadata` + `TKBCompilerInformation` — deterministic artifact IDs (UUID5) |
| `loaders.py` | Reads upstream compiler artifacts from state modules |
| `statistics.py` | 9 statistics blocks (concept, unit, graph, runtime, nav, validation, memory, quality, build) |
| `validation.py` | 9 validation passes (schema, reference, ownership, authority, graph, cross-ref, serialization, artifact, build) |
| `serialization.py` | Deterministic canonical JSON + SHA-256 fingerprint |
| `state.py` | Module-level state (run-scoped, same idiom as `artifact_manager/state.py`) |
| `registry.py` | Artifact Manager integration + Build Manifest attachment |
| `exceptions.py` | Exception hierarchy (`TKBBuildError`, `TKBValidationError`, etc.) |

---

## Integration Flow

### Inputs (read from existing state modules, no modification)

```python
artifact_manager.state    # get_current_build()
build_metadata.state      # get_current_build_metadata()
cache.state               # get_current_cache_entry() -> OptimizedKnowledgePackage
change_detection.state    # get_current_change_detection_report()
canonicalization          # canonical_json, sha256_hexdigest, strip_volatile (reused)
```

### Output (written to TKB-owned state)

```python
teacher_knowledge_base.state  # set_current_tkb_result()
```

### No previous milestone was modified.

---

## Validation Flow

Each validation pass produces `{"passed": bool, "violations": [...]}`. All passes are run unconditionally. Results are aggregated in `validation.passed`.

1. **schema_validation** — required fields present, correct types
2. **reference_validation** — all IDs referenced exist in their target index
3. **ownership_validation** — no concept owned by multiple chapters (Authority Matrix)
4. **authority_validation** — unit IDs don't collide with concept IDs
5. **graph_validation** — no broken edges, no self-loops; cycles documented
6. **cross_reference_validation** — navigation/runtime indexes consistent with EKG/units
7. **serialization_validation** — all outputs JSON-serializable
8. **artifact_validation** — artifact_id and schema_version present
9. **build_validation** — all required pipeline stages completed

By default, validation errors are recorded in `diagnostics` and the artifact is still produced. Set `config.strict_validation=True` to raise `TKBValidationError` on any violation.

---

## Serialization Flow

1. `artifact.to_dict()` — deterministic Python dict, stable key order
2. `canonicalization.canonical_json()` — compact JSON, `sort_keys=True`
3. `canonicalization.strip_volatile()` + extra volatile strip → SHA-256 → content fingerprint
4. `sha256_hexdigest(canonical_json_str)` → serialization fingerprint

Volatile fields excluded from fingerprinting: `generated_at`, `serialized_at`, `stage_timings_seconds`, `total_build_time_seconds` (wall-clock measurements that change per run).

---

## Determinism

- All artifact IDs: UUID5 (content-derived, never random)
- All list ordering: stable (sorted by content keys — concept IDs, chapter keys, etc.)
- All serialization: `canonical_json()` + `sort_keys=True`
- Fingerprinting: `sha256_hexdigest(canonical_json(strip_volatile(artifact_dict)))`
- **Identical inputs always produce identical artifacts**

---

## Testing Strategy

Test files are in `tests/`:

| Test file | Coverage |
|-----------|---------|
| `conftest.py` | Shared deterministic fixtures (12 concepts, 2 chapters) |
| `test_tkb_unit.py` | Unit tests for each module in isolation |
| `test_tkb_builders.py` | Builder-level tests for each of the 8 pipeline stages |
| `test_tkb_integration.py` | Full pipeline integration, determinism, validation, regression, multi-chapter |

**Run tests:**
```bash
cd project_root
python -m pytest tests/ -v
```

Test categories:
- **Unit tests** — exceptions, metadata, context, artifact, serialization, state
- **Builder tests** — each stage independently, including fallback behavior
- **Integration tests** — full end-to-end pipeline with 12-concept, 2-chapter fixture
- **Determinism tests** — same input → same artifact_id → same fingerprint
- **Validation tests** — schema complete, no duplicate ownership, cross-reference integrity
- **Regression tests** — canonicalization, artifact_manager, change_detection, build_executor unchanged

---

## Usage Examples

### Standard build (from live compiler run)

```python
# After pipeline has run Phases A-E5 and state modules are populated:
from teacher_knowledge_base.builder import build_teacher_knowledge_base

result = build_teacher_knowledge_base(
    build=current_build,    # from artifact_manager.state.get_current_build()
    storage=storage,        # OneDriveStorage for persistence
)

artifact = result.artifact
print(artifact.get_artifact_id())   # deterministic UUID5
print(artifact.get_teaching_unit_count())
print(result.fingerprint)           # SHA-256 content fingerprint
```

### Standalone / testing build

```python
from teacher_knowledge_base.builder import build_teacher_knowledge_base

result = build_teacher_knowledge_base(
    config={
        "source_artifact_id": "build-001",
        "pipeline_version": "M6.1.0",
        "chapter_ids": ["ch1", "ch2"],
    },
    direct_artifacts={
        "knowledge_graph": kg_dict,
        "document_structure_tree": dst_dict,
        "optimized_knowledge_package": okp_dict,
    },
)
```

### Access runtime indexes

```python
# O(1) concept lookup
concept = artifact.runtime_indexes["concept_by_id"]["concept-id-here"]

# O(1) unit lookup
unit = artifact.runtime_indexes["teaching_unit_by_id"]["unit-id-here"]

# Prerequisite chain
prereqs = artifact.runtime_indexes["prerequisite_index"]["concept-id"]

# Teaching sequence for a chapter
units_in_order = artifact.runtime_indexes["teaching_unit_by_chapter"]["ch1"]
```

### Serialize to JSON

```python
from teacher_knowledge_base.serialization import artifact_to_json

json_str = artifact_to_json(result.artifact)
with open("teacher_knowledge_base.json", "w") as f:
    f.write(json_str)
```

---

## Architecture Constraints (M6.1 rules)

- ❌ No Phase 2 runtime implementation
- ❌ No StudentLearningState, PedagogyProfile, adaptive tutoring, search
- ❌ No redesign of frozen architecture specifications
- ❌ No random UUIDs — all IDs are UUID5 (content-derived)
- ❌ No modification of previous milestone modules
- ✅ Architecture frozen at M6.0.3 — this is implementation only

---

## Frozen Architecture Specifications

These documents define the implementation contract (not modified):

- `M6_ARCHITECTURE_SPECIFICATION.md`
- `TEACHER_KNOWLEDGE_BASE_SCHEMA.md`
- `AUTHORITY_MATRIX.md`
- `ENRICHED_DST_SPECIFICATION.md`
- `ENRICHED_KNOWLEDGE_GRAPH_SPECIFICATION.md`
- `ENRICHED_DEPENDENCY_GRAPH_SPECIFICATION.md`
- `LEARNING_GRAPH_SPECIFICATION.md`
- `CURRICULUM_GRAPH_SPECIFICATION.md`
- `TEACHING_UNIT_SPECIFICATION.md`
- `NAVIGATION_SYSTEM_SPECIFICATION.md`
- `RUNTIME_API_SPECIFICATION.md`
- `PHASE2_INTEGRATION_GUIDE.md`
