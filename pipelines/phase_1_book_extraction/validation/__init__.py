"""
validation/ — Phase D1: System Integrity Validation.

SCOPE: this package holds the one Phase D artifact that exists so far --
`system_integrity.py` -- plus its own state module (`state.py`), mirroring
the `compiler/` and `knowledge_graph/` packages' own top-level layout
(a validation-style module + a state module, imported by pipeline.py at
one integration point).

This package is intentionally thin: it contains no compiler logic, no
knowledge graph logic, and no educational-object logic of its own. Every
check `system_integrity.py` performs reads artifacts Phase B (compiler/)
and Phase C (knowledge_graph/) have already computed -- it never
recomputes or duplicates a check either of those packages already makes.
"""
