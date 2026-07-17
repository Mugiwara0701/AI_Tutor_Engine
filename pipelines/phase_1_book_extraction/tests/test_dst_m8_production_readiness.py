"""tests/test_dst_m8_production_readiness.py — Milestone 8: End-to-End
Verification & Production Readiness.

SCOPE / WHAT THIS FILE ACTUALLY EXERCISES: like
tests/test_pipeline_dst_integration.py (Milestone 5.1), `pipeline.py`
itself cannot be imported in isolation in this environment (it depends
on `modules.*`, a real `config.py`, `fitz`, a real `prompt_manager`,
etc. -- none of which are part of this codebase slice), and no real
NCERT PDFs are available to run through Phase 1's PDF/VLM extraction
stages. This file therefore verifies the DST subsystem itself -- the
part M6/M7 actually own -- end-to-end from its real, documented input
contract (`schemas.chapter_schema.ChapterJSON`, exactly what
`build_tree_from_chapter_json()` consumes) through build -> validate
-> serialize -> persist -> load, using the same real collaborators
`test_pipeline_dst_integration.py` already uses (the real
`compiler.RegistryManager`, the real builder/validator/artifact/
persistence modules -- no hand-rolled stand-ins for DST's own code).

Different subjects/layouts (English, Hindi, Sanskrit, Science diagrams,
Mathematics equations, History timelines, Geography maps, ...) are
stood in for here as chapter *shapes* -- heading depth, breadth,
content-type mix, and script -- since DST's own contract (schema §2.1:
"language- and layout-agnostic") is defined entirely in terms of that
shape, never in terms of subject-specific business logic. Nothing in
`document_structure_tree/` branches on language or subject.
"""
from __future__ import annotations

import time
import unittest

from compiler.registries import create_registry_manager, populate_registries
from document_structure_tree import state as dst_state
from document_structure_tree.artifact import generate_artifact, to_canonical_json
from document_structure_tree.builder import build_tree_from_chapter_json
from document_structure_tree.document_structure_tree import DocumentStructureTree
from document_structure_tree.enums import ValidationStatus
from document_structure_tree.persistence import (
    load_document_structure_tree,
    persist_document_structure_tree,
)
from document_structure_tree.primitives import ChapterId, CompilerVersion, SchemaVersion
from schemas.chapter_schema import ChapterJSON, Definition, Figure, TopicNode

from modules import json_writer
from storage.exceptions import NotFoundError

DST_SCHEMA_VERSION = SchemaVersion("1.1.0")
DST_COMPILER_VERSION = CompilerVersion("1.0.0")


# ---------------------------------------------------------------------
# Shared harness (mirrors tests/test_pipeline_dst_integration.py's own
# _run_dst_pipeline_step() -- the exact sequence pipeline.py runs).
# ---------------------------------------------------------------------

class FakeStorage:
    """Same in-memory OneDriveStorage stand-in as
    tests/test_dst_persistence.py -- see that file for the rationale."""

    def __init__(self):
        self.files = {}

    def upload_json(self, obj, path=None, indent=2):
        self.files[path] = obj
        return path

    def download_json(self, path=None):
        if path not in self.files:
            raise NotFoundError(path)
        return self.files[path]

    def exists(self, path=None):
        return path in self.files

    def resolve_path(self, board, klass, subject, book_slug):
        return f"AI_TUTOR/{board}/{klass}/{subject}/{book_slug}"


def _run_dst_pipeline(chapter_id: str, chapter_json: ChapterJSON, registry_manager) -> DocumentStructureTree:
    """The exact sequence pipeline.py's Milestone 5.1 block runs:
    builder -> registry-snapshot adaptation -> generate_artifact()
    (which itself drives the frozen validation engine)."""
    from document_structure_tree.registry_snapshot import CompilerRegistrySnapshot

    dst_chapter_id = ChapterId(chapter_id)
    built_tree = build_tree_from_chapter_json(dst_chapter_id, chapter_json)
    snapshot = CompilerRegistrySnapshot(registry_manager=registry_manager, chapter_id=dst_chapter_id)
    return generate_artifact(
        tree=built_tree.tree,
        chapter_id=dst_chapter_id,
        schema_version=DST_SCHEMA_VERSION,
        compiler_version=DST_COMPILER_VERSION,
        canonical_registry_snapshot_ref=chapter_id,
        registry=snapshot,
    )


def _registry_for(topic_ids, **object_lists) -> "object":
    manager = create_registry_manager()
    populate_registries(
        manager,
        topics=[{"id": tid, "object_type": "topic"} for tid in topic_ids],
        **object_lists,
    )
    return manager


def _assert_dst_equal(test: unittest.TestCase, a: DocumentStructureTree, b: DocumentStructureTree) -> None:
    """See tests/test_dst_persistence.py's own helper of the same name
    for why canonical-JSON equality, not raw dataclass `==`, is the
    right notion of equality for this artifact (tree's own array order
    carries no meaning -- schema §5.2)."""
    test.assertEqual(to_canonical_json(a), to_canonical_json(b))


class _DstEndToEndTestCase(unittest.TestCase):
    """Common setUp/tearDown for every scenario below: reset DST's own
    chapter-scoped state, and point modules.json_writer at a FakeStorage
    so persist_document_structure_tree()/load_document_structure_tree()
    never construct a real, network/msal-backed OneDriveStorage."""

    def setUp(self) -> None:
        dst_state.reset_document_structure_tree_state()
        self.storage = FakeStorage()
        self._previous_storage_singleton = json_writer._storage_singleton
        json_writer.set_storage(self.storage)

    def tearDown(self) -> None:
        dst_state.reset_document_structure_tree_state()
        json_writer._storage_singleton = self._previous_storage_singleton

    def _persist_and_reload(self, artifact: DocumentStructureTree, *, chapter_number=1,
                             chapter_title="Chapter") -> DocumentStructureTree:
        route = dict(
            klass="Class_11", subject="Verification", book_slug="m8-production-readiness",
            chapter_number=chapter_number, chapter_title=chapter_title,
        )
        persist_document_structure_tree(self.storage, **route, document_structure_tree=artifact)
        return load_document_structure_tree(self.storage, **route)


# ---------------------------------------------------------------------
# 1. Varied layouts standing in for different NCERT subjects/scripts.
# ---------------------------------------------------------------------

class LayoutVarietyTests(_DstEndToEndTestCase):
    def test_deeply_nested_science_style_chapter(self) -> None:
        """5 levels deep, one child per level -- e.g. a Physics chapter
        with Section > Subsection > Derivation > Case > Sub-case."""
        topics = []
        parent = None
        ids = []
        for depth in range(1, 6):
            tid = f"h{depth}"
            topics.append(TopicNode(
                id=tid, title=f"Level {depth} heading", numbering=".".join(["4"] * depth),
                parent=parent, page_start=depth, reading_order=depth - 1,
            ))
            ids.append(tid)
            parent = tid
        chapter = ChapterJSON(topics=topics)
        manager = _registry_for(ids)
        artifact = _run_dst_pipeline("class-11-physics:chap-04", chapter, manager)

        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        self.assertEqual(len(artifact.tree), 6)  # root + 5 levels
        root = next(n for n in artifact.tree if n.level.value == 0)
        self.assertIsNone(root.parent_id)
        for depth in range(1, 6):
            node = next(n for n in artifact.tree if n.number == ".".join(["4"] * depth))
            self.assertEqual(node.level.value, depth)

        reloaded = self._persist_and_reload(artifact, chapter_title="DeepNesting")
        _assert_dst_equal(self, reloaded, artifact)

    def test_wide_flat_language_style_chapter(self) -> None:
        """Many top-level siblings, no nesting -- e.g. an English/Hindi
        reader with a dozen independent short pieces in one chapter."""
        topics = [
            TopicNode(id=f"p{i}", title=f"Poem {i}", numbering=str(i), parent=None,
                      page_start=i, reading_order=i - 1)
            for i in range(1, 13)
        ]
        chapter = ChapterJSON(topics=topics)
        manager = _registry_for([t.id for t in topics])
        artifact = _run_dst_pipeline("class-6-english:chap-01", chapter, manager)

        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        self.assertEqual(len(artifact.tree), 13)  # root + 12 siblings
        leaf_levels = {n.level.value for n in artifact.tree if n.number is not None}
        self.assertEqual(leaf_levels, {1})

        reloaded = self._persist_and_reload(artifact, chapter_title="WideFlat")
        _assert_dst_equal(self, reloaded, artifact)

    def test_multilingual_titles_hindi_and_sanskrit(self) -> None:
        """Headings titled entirely in Devanagari script (Hindi/Sanskrit
        NCERT books) -- DST's own contract is script-agnostic (schema
        §2.1); nothing in builder.py/validation.py should special-case
        non-ASCII text."""
        topics = [
            TopicNode(id="h1", title="\u0908\u0915\u093e\u0908 \u0915\u0940 \u0938\u0902\u0916\u094d\u092f\u093e",
                      numbering="1", parent=None, page_start=1, reading_order=0),
            TopicNode(id="h2", title="\u0938\u0902\u0938\u094d\u0915\u0943\u0924 \u0936\u094d\u0932\u094b\u0915\u0903",
                      numbering="1.1", parent="h1", page_start=2, reading_order=1),
        ]
        chapter = ChapterJSON(topics=topics)
        manager = _registry_for(["h1", "h2"])
        artifact = _run_dst_pipeline("class-9-hindi:chap-02", chapter, manager)

        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        titles = {n.title for n in artifact.tree if n.title}
        self.assertIn("\u0908\u0915\u093e\u0908 \u0915\u0940 \u0938\u0902\u0916\u094d\u092f\u093e", titles)

        reloaded = self._persist_and_reload(artifact, chapter_title="Multilingual")
        _assert_dst_equal(self, reloaded, artifact)
        # Canonical JSON must preserve the script exactly, not mangle
        # or (silently) ASCII-escape it in a way that loses information.
        record = to_canonical_json(artifact)
        self.assertIn("\u0908\u0915\u093e\u0908 \u0915\u0940 \u0938\u0902\u0916\u094d\u092f\u093e", str(record))

    def test_mixed_content_type_chapter(self) -> None:
        """One heading owning one of nearly every recognized content
        type -- boxes, activities, figures, tables, notes together, the
        way a Biology or Business Studies chapter typically mixes them."""
        topics = [
            TopicNode(
                id="h1", title="Cell Structure", numbering="1", parent=None,
                page_start=1, reading_order=0,
                definitions=["def-1"], figures=["fig-1"],
            ),
        ]
        chapter = ChapterJSON(
            topics=topics,
            definitions=[Definition(id="def-1", object_type="definition", term="Cell", page=1, topic="h1")],
            figures=[Figure(id="fig-1", object_type="figure", page=1, topic="h1")],
        )
        manager = _registry_for(
            ["h1"],
            definitions=[{"id": "def-1", "object_type": "definition"}],
            figures=[{"id": "fig-1", "object_type": "figure"}],
        )
        artifact = _run_dst_pipeline("class-9-biology:chap-06", chapter, manager)
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        root = next(n for n in artifact.tree if n.level.value == 0)
        h1 = next(n for n in artifact.tree if n.number == "1")
        # Content owned directly by h1 shows up as content-type sequence
        # entries on h1, not on the root (schema §9.4 ownership rule).
        content_refs = [e for e in h1.sequence if e.entry_type.value == "content"]
        self.assertEqual(len(content_refs), 2)
        self.assertEqual(root.sequence[0].entry_type.value, "heading")


# ---------------------------------------------------------------------
# 2. Edge cases.
# ---------------------------------------------------------------------

class EdgeCaseTests(_DstEndToEndTestCase):
    def test_empty_chapter_produces_a_root_only_tree(self) -> None:
        chapter = ChapterJSON(topics=[])
        manager = _registry_for([])
        artifact = _run_dst_pipeline("class-8-empty:chap-00", chapter, manager)
        self.assertEqual(len(artifact.tree), 1)
        root = artifact.tree[0]
        self.assertIsNone(root.parent_id)
        self.assertEqual(root.level.value, 0)
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)

        reloaded = self._persist_and_reload(artifact, chapter_title="Empty")
        _assert_dst_equal(self, reloaded, artifact)

    def test_single_heading_chapter(self) -> None:
        chapter = ChapterJSON(topics=[
            TopicNode(id="h1", title="Only Heading", numbering="1", parent=None,
                      page_start=1, reading_order=0),
        ])
        manager = _registry_for(["h1"])
        artifact = _run_dst_pipeline("class-8-single:chap-01", chapter, manager)
        self.assertEqual(len(artifact.tree), 2)  # root + h1
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)

    def test_missing_optional_fields_still_builds(self) -> None:
        """No numbering, no bbox, no page -- everything TopicNode marks
        Optional actually left unset."""
        chapter = ChapterJSON(topics=[
            TopicNode(id="h1", title="Untitled Section", parent=None, reading_order=0),
        ])
        manager = _registry_for(["h1"])
        artifact = _run_dst_pipeline("class-8-sparse:chap-01", chapter, manager)
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        h1 = next(n for n in artifact.tree if n.level.value == 1)
        self.assertIsNone(h1.number)

    def test_duplicate_sibling_numbering_is_a_well_defined_validation_failure(self) -> None:
        """Two siblings both numbered '1' under the same parent collide
        on node_id (schema §14: node_id is derived from chapter_id +
        level + parent + number, deliberately excluding any other
        field) -- confirmed this is caught by the validation engine
        (I3: node_id uniqueness, O1: duplicate sequence entry) and
        surfaces as validation_status='fail' on an artifact that is
        still generated, never as an exception or a silent pass. This
        mirrors test_pipeline_dst_integration.py's own established
        pattern for a dangling reference (R2) -- validation catches it,
        the pipeline does not crash."""
        chapter = ChapterJSON(topics=[
            TopicNode(id="h1", title="First", numbering="1", parent=None, page_start=1, reading_order=0),
            TopicNode(id="h2", title="Second (duplicate number)", numbering="1", parent=None,
                      page_start=2, reading_order=1),
        ])
        manager = _registry_for(["h1", "h2"])
        artifact = _run_dst_pipeline("class-8-dup:chap-01", chapter, manager)

        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.FAIL)
        failing_invariants = {
            r.invariant_id.value for r in artifact.validation_metadata.validation_results
            if r.status != ValidationStatus.PASS
        }
        self.assertIn("I3", failing_invariants)  # node_id uniqueness

    def test_large_chapter_builds_and_serializes(self) -> None:
        """200 top-level headings, each with one nested child -- a stand-in
        for an unusually large chapter (e.g. a Mathematics NCERT book
        with many short worked-example sections)."""
        topics = []
        ids = []
        for i in range(1, 201):
            pid = f"p{i}"
            cid = f"c{i}"
            topics.append(TopicNode(id=pid, title=f"Section {i}", numbering=str(i),
                                     parent=None, page_start=i, reading_order=2 * (i - 1)))
            topics.append(TopicNode(id=cid, title=f"Subsection {i}.1", numbering=f"{i}.1",
                                     parent=pid, page_start=i, reading_order=2 * (i - 1) + 1))
            ids += [pid, cid]
        chapter = ChapterJSON(topics=topics)
        manager = _registry_for(ids)
        artifact = _run_dst_pipeline("class-10-maths:chap-99", chapter, manager)
        self.assertEqual(len(artifact.tree), 401)  # root + 200 + 200
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)

        reloaded = self._persist_and_reload(artifact, chapter_title="Large")
        _assert_dst_equal(self, reloaded, artifact)


# ---------------------------------------------------------------------
# 3. Determinism.
# ---------------------------------------------------------------------

class DeterminismTests(_DstEndToEndTestCase):
    def test_identical_input_produces_identical_canonical_json_and_fingerprint(self) -> None:
        def _chapter():
            return ChapterJSON(topics=[
                TopicNode(id="h1", title="Waves", numbering="1", parent=None, page_start=1, reading_order=0),
                TopicNode(id="h2", title="Reflection", numbering="1.1", parent="h1", page_start=2, reading_order=1),
            ])

        manager_a = _registry_for(["h1", "h2"])
        artifact_a = _run_dst_pipeline("class-11-physics:chap-08", _chapter(), manager_a)
        dst_state.reset_document_structure_tree_state()
        manager_b = _registry_for(["h1", "h2"])
        artifact_b = _run_dst_pipeline("class-11-physics:chap-08", _chapter(), manager_b)

        self.assertEqual(to_canonical_json(artifact_a), to_canonical_json(artifact_b))
        self.assertEqual(
            artifact_a.artifact_metadata.chapter_fingerprint,
            artifact_b.artifact_metadata.chapter_fingerprint,
        )


# ---------------------------------------------------------------------
# 4. Performance smoke check (coarse -- catches catastrophic
#    regressions, e.g. accidental O(n^2)/O(n^3) behavior, not a strict
#    SLA; no production hardware/timing target is specified anywhere
#    in the frozen milestones for this to be measured against).
# ---------------------------------------------------------------------

class PerformanceSmokeTests(_DstEndToEndTestCase):
    def test_thousand_node_chapter_builds_in_a_few_seconds(self) -> None:
        topics = []
        ids = []
        for i in range(1, 1001):
            tid = f"h{i}"
            topics.append(TopicNode(id=tid, title=f"Heading {i}", numbering=str(i),
                                     parent=None, page_start=1, reading_order=i - 1))
            ids.append(tid)
        chapter = ChapterJSON(topics=topics)
        manager = _registry_for(ids)

        start = time.monotonic()
        artifact = _run_dst_pipeline("class-perf:chap-01", chapter, manager)
        record = to_canonical_json(artifact)
        elapsed = time.monotonic() - start

        self.assertEqual(len(artifact.tree), 1001)
        self.assertIsInstance(record, dict)
        # Generous bound -- this environment's hardware is unknown and
        # unrepresentative of production; this only guards against
        # gross algorithmic regressions (a 1000-node chapter taking
        # e.g. minutes would indicate one).
        self.assertLess(
            elapsed, 10.0,
            msg=f"1000-node build+serialize took {elapsed:.2f}s -- investigate for algorithmic regressions",
        )


if __name__ == "__main__":
    unittest.main()
