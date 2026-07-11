"""
build_metadata/ — Phase E1: Build Metadata.

SCOPE: this package holds the Phase E1 artifact -- BuildMetadata -- and
the four sub-metadata blocks it aggregates:

  * `compilation_metadata.py` -- CompilationMetadata: operational build
    metadata (source PDF, content hash, start/end time, CLI invocation,
    batch configuration). Never participates in any fingerprint.
  * `configuration_metadata.py` -- ConfigurationMetadata: deterministic
    configuration metadata (compiler/model configuration, prompt
    versions, extraction-policy-relevant settings, deterministic
    thresholds, feature flags), plus one deterministic configuration
    fingerprint derived via canonicalization.py (the same shared
    canonicalization primitives compiler/fingerprints.py,
    knowledge_graph/fingerprints.py, and validation/determinism.py
    already use -- no second fingerprint implementation).
  * `version_metadata.py` -- VersionMetadata: aggregates already-existing
    version markers (compiler version, schema version, per-phase version
    markers, phase completion status) from Phases B-D3. Never redeclares
    or modifies any of them.
  * `build.py` -- CompilerMetadata + GraphMetadata (read-only aggregation
    of the compiler's and knowledge graph's own already-computed
    manifest/statistics/fingerprints/readiness-report/build-summary/
    final-status artifacts) and BuildMetadata itself, the top-level
    aggregation of all five blocks above. `finalize_build_metadata()` is
    the one pipeline.py integration point (mirrors compiler/finalize.py's
    and validation/release.py's own "single aggregation call" shape, one
    layer up).
  * `state.py` -- the module-level "current chapter's BuildMetadata"
    slot, following the exact idiom compiler/state.py,
    knowledge_graph/state.py, and validation/state.py /
    validation/release_state.py already establish.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
Dependency Graph (E2), not Change Detection (E3), not Incremental
Compilation (E4), not Metadata Validation, not a Build Cache. Phase E1 is
an aggregation layer ONLY -- it never regenerates, repairs, recomputes,
or mutates a single field anywhere in the Compiler IR, the Knowledge
Graph, any earlier report, or Chapter JSON, and it never inserts into,
updates, or removes from any registry.

REUSE, DON'T RECOMPUTE (mirrors every earlier phase's own rule, applied
one layer up): every compiler/graph field BuildMetadata carries is read
from artifacts Phases B-D3 already produced this chapter -- the Compiler
Manifest/Statistics/Fingerprints/Readiness Report/Build Summary/Final
Status, and the Knowledge Graph's own equivalents. Nothing here re-scans
a registry, re-derives a fingerprint, or re-validates anything a second
time.
"""