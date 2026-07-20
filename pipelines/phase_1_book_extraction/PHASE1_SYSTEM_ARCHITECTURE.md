# PHASE 1 SYSTEM ARCHITECTURE — AI-Native Educational Compiler
**Version:** Phase 1 Release Candidate (M5.5)
**Date:** 2026-07-20

---

## 1. COMPLETE COMPILER ARCHITECTURE

The Phase 1 compiler is a multi-stage, deterministic, PDF-to-Knowledge-Artifact
pipeline. It transforms raw educational PDFs (NCERT textbooks) into structured,
validated, serialized knowledge packages ready for M6 Teacher Knowledge Base
Construction.

### Core Design Principles
- **Determinism**: Identical inputs always produce byte-identical outputs
- **Additive layering**: Each milestone adds on top of frozen prior milestones
- **Read-only consumers**: Downstream phases read upstream artifacts, never mutate them
- **Chapter-scoped state**: All internal state is chapter-scoped and reset between chapters
- **Registry-based identity**: All canonical objects are identified by deterministic UUIDs

---

## 2. MODULE DEPENDENCY GRAPH

```
                    ┌─────────────┐
                    │  pipeline.py │ (main orchestrator)
                    └──────┬──────┘
                           │ imports/calls all below
    ┌──────────────────────┼──────────────────────────┐
    │                      │                           │
    ▼                      ▼                           ▼
modules/           compiler/               knowledge_graph/
  pdf_parser         registries               build_nodes
  layout_detector    enrichment               build_edges
  ocr_engine         normalization            validation
  stage_a-e          references               build
  semantic_proc      relationships            fingerprints
  graph_builder      validation               finalize
  json_writer        build                    state
  equation_intent    fingerprints
  canonical          finalize
  topic_linker       state

    ▼                      ▼                           ▼
document_structure_  dependency_graph/        change_detection/
  tree/               build                    engine
  builder             identity                 compare
  artifact            node/edge               snapshot
  persistence         registries              traversal
  validation          schema                  state
  state               state

    ▼                      ▼                           ▼
incremental_         incremental_compilation_ validation/
  compilation/        validation/              system_integrity
  planner             engine                   determinism
  traversal           validator                release
  engine              state                    state modules
  state

    ▼                      ▼                           ▼
build_metadata/      runtime/                 artifact_manager/
  build               runtime                  build
  finalize            context                  manifest
  persistence         state                    persistence
  state               exceptions               state

    ▼                      ▼                           ▼
build_executor/      cache/                   compiler_release/
  executor            index                    finalize
  plan                reuse                    report
  report              validation               persistence
  state               state                    state

    ▼ (M5.5 integration — additive)
modules/
  educational_object_framework/   (M5.1)
  educational_taxonomy/           (M5.2A)
  subject_profile_framework/      (M5.2B)
  structural_understanding_engine/(M5.2C)
  semantic_interpretation_engine/ (M5.2D)
  relationship_discovery_engine/  (M5.2E) → SemanticGraph
  master_knowledge_compiler/      (M5.3)  → MasterKnowledgePackage
  knowledge_optimization/         (M5.4)  → OptimizedKnowledgePackage
```

---

## 3. ARTIFACT DEPENDENCY GRAPH

```
PDF Files
   │
   ▼
Chapter JSON (ChapterJSON / schemas/chapter_schema.py)
   │
   ├──► Compiler IR (RegistryManager — compiler/)
   │         │
   │         ├──► Knowledge Graph (KnowledgeGraph — knowledge_graph/)
   │         │         │
   │         │         └──► Graph Validation Report
   │         │
   │         ├──► Compiler Manifest / Statistics / Fingerprints
   │         ├──► Compiler Validation Report
   │         ├──► Compiler Readiness Report
   │         └──► Compiler Build Summary (finalize_compiler_build)
   │
   ├──► Document Structure Tree (DocumentStructureTree — document_structure_tree/)
   │
   ├──► System Integrity Report (D1 — validation/system_integrity.py)
   ├──► Determinism Report (D2 — validation/determinism.py)
   ├──► Release Readiness Report (D3 — validation/release.py)
   │
   ├──► Build Metadata (build_metadata/)
   │
   ├──► Build Dependency Graph (dependency_graph/)
   ├──► Change Detection Report (change_detection/)
   ├──► Incremental Compilation Plan (incremental_compilation/)
   ├──► Incremental Validation Report (incremental_compilation_validation/)
   ├──► Incremental Finalization Report (incremental_compilation_finalization/)
   │
   ├──► [M5.5] SemanticGraph (relationship_discovery_engine/)
   │         │
   │         └──► MasterKnowledgePackage (master_knowledge_compiler/)
   │                   │
   │                   └──► OptimizedKnowledgePackage (knowledge_optimization/)
   │
   └──► Build (artifact_manager/) → Build Manifest
              │
              └──► CompilerReleaseManifest (compiler_release/) ← PHASE 1 FINAL OUTPUT
```

---

## 4. COMPILER PIPELINE — STAGE BY STAGE

| Stage | Module | Input | Output |
|---|---|---|---|
| PDF Parse | `modules/pdf_parser` | PDF file | Structured page data |
| Layout Detection | `modules/layout_detector` | Page data | Layout regions |
| OCR | `modules/ocr_engine` | Layout regions | Text content |
| Stage A | `modules/stage_a_geometry` | Regions | Geometric segments |
| Stage B | `modules/stage_b_classify` | Segments | Classified blocks |
| Stage C | `modules/stage_c_priority` | Blocks | Prioritized blocks |
| Stage D | `modules/stage_d_extraction` | Blocks | Educational objects |
| Stage E | `modules/stage_e_validation` | Objects | Validated objects |
| JSON Assembly | `modules/json_writer` | All above | `ChapterJSON` |
| Registry Build | `compiler/registries` | `ChapterJSON` | `RegistryManager` |
| Registry Enrichment | `compiler/enrichment` | `RegistryManager` | Enriched registries |
| Registry Normalization | `compiler/normalization` | Registries | Normalized registries |
| Reference Resolution | `compiler/references` | Registries | Resolved references |
| Relationship Resolution | `compiler/relationships` | Registries | Resolved relationships |
| Compiler Validation | `compiler/validation` | Registries | `ValidationReport` |
| Compiler Manifest | `compiler/build` | Registries | `CompilerManifest` |
| Compiler Fingerprints | `compiler/fingerprints` | Manifest | `FingerprintSet` |
| Compiler Finalize | `compiler/finalize` | All above | `CompilerBuildSummary` |
| KG Node Build | `knowledge_graph/build_nodes` | Registries | Graph nodes |
| KG Edge Build | `knowledge_graph/build_edges` | Nodes | Graph edges |
| KG Validation | `knowledge_graph/validation` | Graph | `KGValidationReport` |
| KG Manifest | `knowledge_graph/build` | Graph | `KGManifest` |
| KG Fingerprints | `knowledge_graph/fingerprints` | Manifest | `KGFingerprintSet` |
| KG Finalize | `knowledge_graph/finalize` | All above | `KGBuildSummary` |
| DST Build | `document_structure_tree/builder` | `ChapterJSON` | `DocumentStructureTree` |
| D1 Validation | `validation/system_integrity` | All artifacts | `SystemIntegrityReport` |
| D2 Validation | `validation/determinism` | All artifacts | `DeterminismReport` |
| D3 Release Gate | `validation/release` | D1+D2+prior | `ReleaseReadinessReport` |
| Build Metadata | `build_metadata/build` | All above | `BuildMetadata` |
| Dep Graph | `dependency_graph/build` | All above | `DependencyGraph` |
| Change Detection | `change_detection/engine` | Dep Graph | `ChangeDetectionReport` |
| Incr. Compilation | `incremental_compilation/engine` | Changes | `IncrementalPlan` |
| Incr. Validation | `incremental_compilation_validation` | Plan | `IncrementalValidationReport` |
| Incr. Finalization | `incremental_compilation_finalization` | Validated plan | `IncrementalFinalizationReport` |
| **[M5.5]** EOF Processing | `modules/educational_object_framework` | `ChapterJSON` | `ProcessingPipelineResult` |
| **[M5.5]** Taxonomy Classification | `modules/educational_taxonomy` | Objects | Classified objects |
| **[M5.5]** Structural Analysis | `modules/structural_understanding_engine` | Objects | Structural results |
| **[M5.5]** Semantic Enrichment | `modules/semantic_interpretation_engine` | Structural | `SemanticEnrichmentResult` |
| **[M5.5]** Relationship Discovery | `modules/relationship_discovery_engine` | Enriched | `SemanticGraph` |
| **[M5.5]** MK Compilation | `modules/master_knowledge_compiler` | `SemanticGraph` | `MasterKnowledgePackage` |
| **[M5.5]** KO Optimization | `modules/knowledge_optimization` | `MasterKnowledgePackage` | `OptimizedKnowledgePackage` |
| F1 Runtime | `runtime/runtime` | book_orchestrator | Lifecycle management |
| F2 Artifact Manager | `artifact_manager/build` | All above | `Build` + `BuildManifest` |
| F3 Build Executor | `build_executor/executor` | Per-chapter | `ExecutionPlan` |
| F4 Cache | `cache/` | Build history | Cache entries |
| F5 Release | `compiler_release/finalize` | F1–F4 | `CompilerReleaseManifest` |

---

## 5. PUBLIC API MAP

### compiler/
```python
from compiler import (
    CanonicalRegistry, RegistryManager,
    create_registry_manager, populate_registries,
    get_current_registry_manager, set_current_registry_manager,
    validate_compiler_state, generate_compiler_manifest,
    generate_compiler_statistics, generate_compiler_fingerprints,
    finalize_compiler_build,
)
```

### knowledge_graph/
```python
from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.validation import validate_knowledge_graph
from knowledge_graph.build import generate_knowledge_graph_manifest
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph
```

### modules/master_knowledge_compiler/
```python
from modules.master_knowledge_compiler import compile_graph  # compile_graph(semantic_graph) -> MasterKnowledgePackage
from modules.master_knowledge_compiler import default_compiler  # MasterKnowledgeCompiler instance
```

### modules/knowledge_optimization/
```python
from modules.knowledge_optimization import optimize_package  # optimize_package(pkg) -> OptimizedKnowledgePackage
from modules.knowledge_optimization import default_engine  # KnowledgeOptimizationEngine instance
```

### modules/relationship_discovery_engine/
```python
from modules.relationship_discovery_engine import default_engine  # RelationshipDiscoveryEngine
# default_engine.build_graph(enrichment_results) -> SemanticGraph
```

### validation/
```python
from validation.system_integrity import validate_system_integrity
from validation.determinism import validate_determinism
from validation.release import finalize_release
```

### runtime/
```python
from runtime.runtime import CompilerRuntime
runtime = CompilerRuntime()
runtime.run(use_vlm=True, page_batch_size=4)
runtime.status()
runtime.cancel()
```

---

## 6. ARTIFACT LIFECYCLE

```
CREATION          VALIDATION        PERSISTENCE       REGISTRATION
────────          ──────────        ───────────       ────────────
build.py          validation.py     persistence.py    state.py
(pure function)   (read-only)       (upload_json)     (set_current_*)
      │                 │                 │                 │
      ▼                 ▼                 ▼                 ▼
Dataclass         Report dataclass  OneDrive JSON     Module-level slot
(frozen if        (to_dict())       file              (reset per chapter)
 possible)                          
                                                      artifact_manager/
                                                      build.py reads via
                                                      get_current_*()
                                                      on run completion
```

---

## 7. DATA FLOW

```
External Input:
  PDF file(s) in pdf_in/ → book_orchestrator → pipeline.process_all_pdfs()

Per-chapter:
  pdf_path → process_chapter()
           → OCR + Layout → Stage A/B/C/D/E → ChapterJSON
           → populate_registries() → RegistryManager (in-memory)
           → build_knowledge_graph_nodes/edges() → KnowledgeGraph (in-memory)
           → build_tree_from_chapter_json() → DocumentStructureTree
           → validate_system_integrity/determinism/release()
           → finalize_build_metadata()
           → generate_dependency_graph() → plan_incremental_compilation()
           → validate/finalize_incremental_compilation()
           → persist_registries(), persist_knowledge_graph(), persist_document_structure_tree()
           → [M5.5] educational_object processing → SemanticGraph → MasterKnowledgePackage → OptimizedKnowledgePackage

Per-run (after all chapters):
  stats dict → CompilerRuntime._record_build() → artifact_manager.build.create_build()
             → artifact_manager.manifest.generate_build_manifest()
             → compiler_release.finalize.finalize_release()
             → compiler_release.persistence.persist_release_manifest()

External Output:
  OneDrive storage:
    /<book>/<chapter>/master_json.json         (ChapterJSON)
    /<book>/<chapter>/compiler_registries/     (Compiler IR)
    /<book>/<chapter>/knowledge_graph/         (KnowledgeGraph)
    /<book>/<chapter>/document_structure_tree/ (DST)
    /<book>/<chapter>/build_metadata/          (BuildMetadata)
    /<book>/<chapter>/dependency_graph/        (DependencyGraph)
    /<book>/build_manifest.json                (BuildManifest)
    /release_history/<build_id>/release.json   (CompilerReleaseManifest)
    [M5.5] /master_knowledge/<book>.json       (MasterKnowledgePackage)
    [M5.5] /optimized_knowledge/<book>.json    (OptimizedKnowledgePackage)
```

---

## 8. INTEGRATION POINTS (What M6 Will Consume)

M6 (Teacher Knowledge Base Construction) will consume the following Phase 1 outputs:

| Artifact | Module | What M6 uses |
|---|---|---|
| `OptimizedKnowledgePackage` | `modules/knowledge_optimization` | Primary: concept index, retrieval index, semantic search index, runtime cache, learning analytics, quality report |
| `MasterKnowledgePackage` | `modules/master_knowledge_compiler` | Fallback: raw concept index, dependency map, learning progression, cross-references |
| `ChapterJSON` | `schemas/chapter_schema` | Raw source: topics, concepts, definitions, equations, figures |
| `KnowledgeGraph` | `knowledge_graph/` | Structural graph of educational objects |
| `DocumentStructureTree` | `document_structure_tree/` | Hierarchical chapter structure |
| `CompilerReleaseManifest` | `compiler_release/` | Run-level build verdict and artifact index |
| `BuildManifest` | `artifact_manager/manifest` | Chapter-level artifact locations |

**M6 entry contract:**
- `OptimizedKnowledgePackage.manifest.status == "READY"`
- `CompilerReleaseManifest.final_release_status == "READY"`
- All referenced paths in `BuildManifest` exist in OneDrive storage

---

## 9. COMPILER CONTRACTS

1. **Determinism**: `compile(inputs_A) == compile(inputs_A)` always. No random IDs except `Build.build_id` (which is run-unique by design).

2. **Backward compatibility**: Every public API addition is strictly additive. No existing function signature, data model field, or schema field is changed.

3. **Chapter isolation**: State from chapter N never leaks into chapter N+1. Every `state.py`'s `reset_*_state()` is called before each chapter.

4. **Validation purity**: No validator mutates any artifact. Validation is always a read-only pass.

5. **Registry immutability after build**: Once `populate_registries()` completes and `finalize_compiler_build()` seals the build, no registry is mutated.

6. **Single writer**: Only `pipeline.py` (via orchestrator calls) writes to state modules. No two stages share a writer for the same state slot.
