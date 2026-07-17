"""tests/test_pipeline_dst_integration.py — Milestone 5.1: Compiler
Pipeline Integration.

SCOPE. `pipeline.py` itself cannot be imported in isolation (it depends
on `modules.*`, `config`, `fitz`, and several other Phase 1 packages not
present in this codebase slice -- see `pipeline.py`'s own imports), so
this module does not import it. Instead it exercises exactly the
sequence Milestone 5.1's own integration block runs, in the same order,
against the same real collaborators:

    build_tree_from_chapter_json()  -- invoke the DST builder
    CompilerRegistrySnapshot        -- adapt a real compiler.RegistryManager
    generate_artifact()             -- generate the artifact, which itself
                                        drives Milestone 3's frozen
                                        run_all_invariants() (invoke DST
                                        validation)
    document_structure_tree.state   -- the chapter-scoped "current DST"
                                        lifecycle pipeline.py drives

This mirrors `tests/test_dst_registry_snapshot.py`'s own precedent of
testing a Milestone 5 seam against the REAL `compiler.RegistryManager`
rather than a hand-rolled stand-in, and `schemas.chapter_schema.
ChapterJSON`/`TopicNode`/`Definition` rather than a generic dict, since
those are precisely `build_tree_from_chapter_json()`'s own documented
input contract (see builder.py's own module docstring).

Not covered here (out of Milestone 5.1's own scope -- see this
milestone's own "Do NOT implement" instructions, and
document_structure_tree/persistence.py's own module docstring):
artifact registration, persistence, build metadata changes.
"""
from __future__ import annotations

import unittest

from compiler.registries import create_registry_manager, populate_registries
from document_structure_tree import state as dst_state
from document_structure_tree.artifact import generate_artifact
from document_structure_tree.builder import build_tree_from_chapter_json
from document_structure_tree.enums import ValidationStatus
from document_structure_tree.exceptions import DSTBuildError
from document_structure_tree.primitives import ChapterId, CompilerVersion, SchemaVersion
from document_structure_tree.registry_snapshot import CompilerRegistrySnapshot
from schemas.chapter_schema import ChapterJSON, Definition, Figure, TopicNode

CHAPTER_REFERENCE = "class-11-physics:chap-07"
DST_SCHEMA_VERSION = SchemaVersion("1.1.0")
DST_COMPILER_VERSION = CompilerVersion("1.0.0")


def _well_formed_chapter_json() -> ChapterJSON:
    """One root heading ('h1', numbered '4.1') owning one Definition
    ('def-1'), one child heading ('h2', numbered '4.1.1') owning one
    Figure ('fig-1') -- every content id below is also registered in
    the matching compiler registry by `_populated_manager()`, so R2/R3
    resolve cleanly and the resulting artifact validates 'pass'."""
    topics = [
        TopicNode(
            id="h1", title="Newton's Second Law", numbering="4.1", parent=None,
            page_start=10, page_end=12, reading_order=0,
            bbox={"x0": 0.0, "y0": 100.0, "x1": 0.0, "y1": 0.0, "page": 10},
            definitions=["def-1"],
        ),
        TopicNode(
            id="h2", title="Momentum", numbering="4.1.1", parent="h1",
            page_start=11, page_end=11, reading_order=1,
            bbox={"x0": 0.0, "y0": 50.0, "x1": 0.0, "y1": 0.0, "page": 11},
            figures=["fig-1"],
        ),
    ]
    return ChapterJSON(
        topics=topics,
        definitions=[Definition(id="def-1", object_type="definition", term="Force", page=10, topic="h1")],
        figures=[Figure(id="fig-1", object_type="figure", page=11, topic="h2")],
    )


def _populated_manager() -> "object":
    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[{"id": "h1", "object_type": "topic"}, {"id": "h2", "object_type": "topic"}],
        definitions=[{"id": "def-1", "object_type": "definition"}],
        figures=[{"id": "fig-1", "object_type": "figure"}],
    )
    return manager


def _run_dst_pipeline_step(chapter_json: ChapterJSON, registry_manager) -> "object":
    """The exact sequence pipeline.py's Milestone 5.1 block runs."""
    dst_chapter_id = ChapterId(CHAPTER_REFERENCE)
    built_tree = build_tree_from_chapter_json(dst_chapter_id, chapter_json)
    snapshot = CompilerRegistrySnapshot(registry_manager=registry_manager, chapter_id=dst_chapter_id)
    return generate_artifact(
        tree=built_tree.tree,
        chapter_id=dst_chapter_id,
        schema_version=DST_SCHEMA_VERSION,
        compiler_version=DST_COMPILER_VERSION,
        canonical_registry_snapshot_ref=CHAPTER_REFERENCE,
        registry=snapshot,
    )


class DstPipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        dst_state.reset_document_structure_tree_state()

    def tearDown(self) -> None:
        dst_state.reset_document_structure_tree_state()

    # -- happy path: builder -> validation -> artifact ---------------------

    def test_well_formed_chapter_produces_a_passing_artifact(self) -> None:
        artifact = _run_dst_pipeline_step(_well_formed_chapter_json(), _populated_manager())
        self.assertEqual(
            artifact.validation_metadata.validation_status, ValidationStatus.PASS,
        )
        # root + h1 + h2
        self.assertEqual(len(artifact.tree), 3)

    def test_artifact_metadata_carries_the_chapter_reference(self) -> None:
        artifact = _run_dst_pipeline_step(_well_formed_chapter_json(), _populated_manager())
        self.assertEqual(artifact.artifact_metadata.chapter_id, ChapterId(CHAPTER_REFERENCE))
        self.assertEqual(
            artifact.build_provenance.canonical_registry_snapshot_ref, CHAPTER_REFERENCE,
        )

    # -- validation invoked: a dangling content reference fails, not raises -

    def test_unresolvable_content_reference_yields_a_failing_artifact_not_an_exception(self) -> None:
        """A registry that never registered 'def-1' means R2 cannot
        resolve it -- this must surface as validation_status = 'fail'
        (an artifact, still generated), never as an exception. Proves
        this integration invokes DST validation, not just the builder."""
        manager = create_registry_manager()
        populate_registries(
            manager,
            topics=[{"id": "h1", "object_type": "topic"}, {"id": "h2", "object_type": "topic"}],
            figures=[{"id": "fig-1", "object_type": "figure"}],
            # deliberately omit definitions -- 'def-1' will not resolve
        )
        artifact = _run_dst_pipeline_step(_well_formed_chapter_json(), manager)
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.FAIL)

    # -- failure propagation: a builder precondition failure must raise ----

    def test_duplicate_topic_ids_raise_dstbuilderror(self) -> None:
        """Two topics sharing one source id cannot be assembled into a
        tree at all (a builder precondition, not a §15 invariant) --
        this must propagate as DSTBuildError, exactly as pipeline.py's
        own integration block relies on to fail the chapter rather than
        silently produce a broken DST."""
        chapter = ChapterJSON(
            topics=[
                TopicNode(id="h1", title="A", parent=None, reading_order=0),
                TopicNode(id="h1", title="B (duplicate id)", parent=None, reading_order=1),
            ],
        )
        with self.assertRaises(DSTBuildError):
            _run_dst_pipeline_step(chapter, create_registry_manager())

    # -- state lifecycle: mirrors pipeline.py's reset/set around the call --

    def test_state_slot_is_set_after_a_successful_build(self) -> None:
        self.assertFalse(dst_state.has_current_document_structure_tree())
        artifact = _run_dst_pipeline_step(_well_formed_chapter_json(), _populated_manager())
        dst_state.set_current_document_structure_tree(artifact)
        self.assertTrue(dst_state.has_current_document_structure_tree())
        self.assertIs(dst_state.get_current_document_structure_tree(), artifact)

    def test_state_slot_is_reset_before_the_next_chapter(self) -> None:
        artifact = _run_dst_pipeline_step(_well_formed_chapter_json(), _populated_manager())
        dst_state.set_current_document_structure_tree(artifact)
        dst_state.reset_document_structure_tree_state()
        self.assertFalse(dst_state.has_current_document_structure_tree())


if __name__ == "__main__":
    unittest.main()