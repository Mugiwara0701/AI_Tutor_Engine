"""
validation/ — Phase D1 (System Integrity) & Phase D2 (Determinism &
Reproducibility) Validation.

SCOPE: this package holds two Phase D artifacts:

  * `system_integrity.py` (+ its own state module, `state.py`) -- Phase
    D1: cross-artifact CONSISTENCY across the complete compiler
    pipeline.
  * `determinism.py` (+ its own state module, `determinism_state.py`)
    -- Phase D2: REPRODUCIBILITY, not correctness -- given the same
    already-built compiler/graph state, does re-deriving a fingerprint/
    re-serializing a registry/re-canonicalizing a manifest, statistics
    block, build summary, or the D1 report itself produce a byte-
    identical result?

Both mirror the `compiler/` and `knowledge_graph/` packages' own top-
level layout (a validation-style module + a state module, imported by
pipeline.py at one integration point each, D2's running immediately
after D1's).

This package is intentionally thin: it contains no compiler logic, no
knowledge graph logic, and no educational-object logic of its own.
Every check either module performs reads artifacts Phase B (compiler/),
Phase C (knowledge_graph/), or (for D2's own System Integrity Report
check) Phase D1 has already computed -- neither module recomputes or
duplicates a check any other phase already makes.
"""
