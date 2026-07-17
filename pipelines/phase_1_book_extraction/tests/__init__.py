"""document_structure_tree/tests/ — Milestone 4 artifact-level unit
tests (roadmap M8/M9/M11's own "Unit tests" / "Integration tests"
deliverables), plus a direct conformance check against the frozen
schema document's own §5.6 example instance.

Every earlier milestone's models are exercised here only through their
already-frozen public API (`build_tree`, `run_all_invariants`,
`HeadingNode.to_json`/`from_json`, ...) -- this test package contains
no tree-assembly, validation-engine, or model changes of its own,
consistent with this milestone's package-boundary instructions.
"""