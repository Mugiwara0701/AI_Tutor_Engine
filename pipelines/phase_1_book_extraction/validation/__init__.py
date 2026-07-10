"""
validation/ — Phase D1 (System Integrity), Phase D2 (Determinism &
Reproducibility), & Phase D3 (Release Readiness) Validation.

SCOPE: this package holds three Phase D artifacts:

  * `system_integrity.py` (+ its own state module, `state.py`) -- Phase
    D1: cross-artifact CONSISTENCY across the complete compiler
    pipeline.
  * `determinism.py` (+ its own state module, `determinism_state.py`)
    -- Phase D2: REPRODUCIBILITY, not correctness -- given the same
    already-built compiler/graph state, does re-deriving a fingerprint/
    re-serializing a registry/re-canonicalizing a manifest, statistics
    block, build summary, or the D1 report itself produce a byte-
    identical result?
  * `release.py` (+ its own state module, `release_state.py`) -- Phase
    D3: the FINAL RELEASE GATE -- given the already-computed Compiler/
    Knowledge Graph Validation, Readiness, Build Summary, Manifest,
    Fingerprint, and Statistics reports, plus the D1 System Integrity
    Report and the D2 Determinism Report, is this compiler output ready
    for Phase E? D3 performs no new validation, determinism, or
    correctness checking of its own -- it only aggregates the verdicts
    D1/D2 (and every earlier phase) already computed into one final
    Release Decision.

All three mirror the `compiler/` and `knowledge_graph/` packages' own
top-level layout (a validation-style module + a state module, imported
by pipeline.py at one integration point each, D2's running immediately
after D1's, and D3's running immediately after D2's).

This package is intentionally thin: it contains no compiler logic, no
knowledge graph logic, and no educational-object logic of its own.
Every check any module here performs reads artifacts Phase B
(compiler/), Phase C (knowledge_graph/), or (for D2's own System
Integrity Report check, and for D3's own System Integrity Report /
Determinism Report aggregation) Phase D1/D2 have already computed --
no module here recomputes or duplicates a check any other phase already
makes.
"""
