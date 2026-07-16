"""document_structure_tree/tests/test_generate_artifact.py — Milestone
4: `generate_artifact()` (roadmap M8/M9; schema §2.2-2.5)."""
from __future__ import annotations

import unittest
from dataclasses import replace

from document_structure_tree import (
    ArtifactMetadata,
    ChapterId,
    CompilerVersion,
    DocumentStructureTree,
    DSTArtifactError,
    HeadingDetectionEntry,
    HeadingDetectionMethod,
    IDENTITY_SCHEME_VERSION,
    IdentitySchemeVersion,
    NodeId,
    SchemaVersion,
    Timestamp,
    ValidationStatus,
    compute_chapter_fingerprint,
    generate_artifact,
)

from .fixtures import (
    BUILD_TIMESTAMP,
    CHAPTER_ID,
    COMPILER_VERSION,
    REGISTRY_REF,
    SCHEMA_VERSION,
    build_small_clean_tree,
    clean_registry,
)


class GenerateArtifactHappyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.built = build_small_clean_tree()
        self.registry = clean_registry()

    def test_produces_a_document_structure_tree(self) -> None:
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=self.registry,
        )
        self.assertIsInstance(artifact, DocumentStructureTree)

    def test_validation_status_pass_for_a_clean_tree(self) -> None:
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=self.registry,
        )
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.PASS)
        for result in artifact.validation_metadata.validation_results:
            self.assertEqual(
                result.status, ValidationStatus.PASS,
                msg=f"{result.invariant_id.value} unexpectedly failed: "
                f"{[v.message for v in (result.violations or ())]}",
            )

    def test_artifact_metadata_populated_exactly_as_given(self) -> None:
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=self.registry,
        )
        meta = artifact.artifact_metadata
        self.assertEqual(meta.schema_version, SCHEMA_VERSION)
        self.assertEqual(meta.compiler_version, COMPILER_VERSION)
        self.assertEqual(meta.identity_scheme_version, IDENTITY_SCHEME_VERSION)
        self.assertEqual(meta.chapter_id, CHAPTER_ID)
        self.assertEqual(meta.build_timestamp, BUILD_TIMESTAMP)

    def test_chapter_fingerprint_matches_validation_s_own_formula(self) -> None:
        """`generate_artifact` must never re-derive its own fingerprint
        formula -- it has to agree, by construction, with Milestone 3's
        `compute_chapter_fingerprint` (B3's precondition)."""
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=self.registry,
        )
        expected = compute_chapter_fingerprint(self.built.tree)
        self.assertEqual(artifact.artifact_metadata.chapter_fingerprint, expected)

    def test_build_provenance_populated(self) -> None:
        entries = (
            HeadingDetectionEntry(
                node_id=self.built.root.node_id,
                method=HeadingDetectionMethod.LAYOUT_ANALYSIS,
            ),
        )
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=self.registry,
            heading_detection_provenance=entries,
        )
        self.assertEqual(artifact.build_provenance.canonical_registry_snapshot_ref, REGISTRY_REF)
        self.assertEqual(artifact.build_provenance.heading_detection_provenance, entries)

    def test_default_build_timestamp_is_a_valid_current_timestamp(self) -> None:
        artifact = generate_artifact(
            tree=self.built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            registry=self.registry,
        )
        # Constructing a Timestamp from it must not raise (proves the
        # generated string satisfies primitives.require_iso8601_utc);
        # already implicitly proven by ArtifactMetadata's own
        # constructor succeeding, re-asserted here for clarity.
        self.assertIsInstance(artifact.artifact_metadata.build_timestamp, Timestamp)
        self.assertTrue(artifact.artifact_metadata.build_timestamp.value.endswith("Z"))


class GenerateArtifactVersionIndependenceTests(unittest.TestCase):
    """Schema §2.3: `schema_version`/`compiler_version`/
    `identity_scheme_version` are mutually independent -- none may be
    inferred from another (roadmap M8's explicit acceptance criterion:
    "independently settable in tests")."""

    def test_each_version_field_independently_settable(self) -> None:
        built = build_small_clean_tree()
        registry = clean_registry()
        artifact = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SchemaVersion("9.9.9"),
            compiler_version=CompilerVersion("0.0.1"),
            identity_scheme_version=IdentitySchemeVersion("some-other-scheme"),
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=registry,
        )
        self.assertEqual(artifact.artifact_metadata.schema_version, SchemaVersion("9.9.9"))
        self.assertEqual(artifact.artifact_metadata.compiler_version, CompilerVersion("0.0.1"))
        self.assertEqual(
            artifact.artifact_metadata.identity_scheme_version,
            IdentitySchemeVersion("some-other-scheme"),
        )
        # None of these three values leaked into, or were derived from,
        # one another.
        self.assertNotEqual(
            artifact.artifact_metadata.schema_version.value,
            artifact.artifact_metadata.compiler_version.value,
        )


class GenerateArtifactPreconditionTests(unittest.TestCase):
    """`DSTArtifactError` preconditions (mirrors `builder.DSTBuildError`
    one milestone earlier) -- distinct from a representable
    `validation_status = 'fail'` outcome; see `GenerateArtifactSeededFailureTests`."""

    def test_empty_tree_raises(self) -> None:
        with self.assertRaises(DSTArtifactError):
            generate_artifact(
                tree=(),
                chapter_id=CHAPTER_ID,
                schema_version=SCHEMA_VERSION,
                compiler_version=COMPILER_VERSION,
                canonical_registry_snapshot_ref=REGISTRY_REF,
                build_timestamp=BUILD_TIMESTAMP,
            )

    def test_dangling_provenance_node_id_raises(self) -> None:
        built = build_small_clean_tree()
        bogus_entry = HeadingDetectionEntry(
            node_id=NodeId("chap-07:does-not-exist"),
            method=HeadingDetectionMethod.TOC_MATCHING,
        )
        with self.assertRaises(DSTArtifactError):
            generate_artifact(
                tree=built.tree,
                chapter_id=CHAPTER_ID,
                schema_version=SCHEMA_VERSION,
                compiler_version=COMPILER_VERSION,
                canonical_registry_snapshot_ref=REGISTRY_REF,
                build_timestamp=BUILD_TIMESTAMP,
                heading_detection_provenance=(bogus_entry,),
                registry=clean_registry(),
            )

    def test_valid_provenance_node_id_does_not_raise(self) -> None:
        built = build_small_clean_tree()
        good_entry = HeadingDetectionEntry(
            node_id=built.root.node_id,
            method=HeadingDetectionMethod.TOC_MATCHING,
        )
        artifact = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            heading_detection_provenance=(good_entry,),
            registry=clean_registry(),
        )
        self.assertEqual(artifact.build_provenance.heading_detection_provenance, (good_entry,))


class GenerateArtifactSeededFailureTests(unittest.TestCase):
    """A tree that fails one or more §15 invariants is not a
    `generate_artifact` error -- it is a normal, fully representable
    `validation_status = 'fail'` artifact (architecture §9.3)."""

    def test_missing_registry_reports_fail_but_still_generates(self) -> None:
        built = build_small_clean_tree()
        # No registry supplied -> R2/R3/R4/B2 all report "could not be
        # verified" as fail (validation.py's own documented policy),
        # without generate_artifact raising anything.
        artifact = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=None,
        )
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.FAIL)
        failed_ids = {
            r.invariant_id.value
            for r in artifact.validation_metadata.validation_results
            if r.status is ValidationStatus.FAIL
        }
        self.assertTrue({"R2", "R3", "R4", "B2"}.issubset(failed_ids))

    def test_seeded_dangling_parent_fails_structural_invariants(self) -> None:
        built = build_small_clean_tree()
        # Corrupt one non-root node's parent_id to point at a node_id
        # that does not exist in the tree at all (S1/S4 dangling-parent
        # case) -- constructing a fresh HeadingNode via `replace` since
        # HeadingNode is frozen and this milestone's own module does
        # not mutate builder output in place.
        broken = tuple(
            replace(node, parent_id=NodeId("chap-07:nonexistent")) if node.number == "4.1.1" else node
            for node in built.tree
        )
        artifact = generate_artifact(
            tree=broken,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=clean_registry(),
        )
        self.assertEqual(artifact.validation_metadata.validation_status, ValidationStatus.FAIL)
        failed_ids = {
            r.invariant_id.value
            for r in artifact.validation_metadata.validation_results
            if r.status is ValidationStatus.FAIL
        }
        self.assertIn("S1", failed_ids)
        # Unrelated invariant categories must not be cross-contaminated
        # by this single seeded failure.
        self.assertNotIn("O1", failed_ids)

    def test_incorrect_chapter_fingerprint_fails_b3_only(self) -> None:
        """B3 is checked by re-deriving the fingerprint independently
        (Milestone 3) and comparing to `artifact_metadata.
        chapter_fingerprint` -- prove `generate_artifact` itself always
        stamps the *correct* one by asserting B3 passes on every
        successful generation (the inverse -- a deliberately wrong
        fingerprint failing B3 -- is exercised directly against
        `validation.check_b3`, Milestone 3's own test surface; this
        module never constructs an `ArtifactMetadata` with an
        incorrect fingerprint itself, by design)."""
        built = build_small_clean_tree()
        artifact = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=clean_registry(),
        )
        b3 = next(
            r for r in artifact.validation_metadata.validation_results if r.invariant_id.value == "B3"
        )
        self.assertEqual(b3.status, ValidationStatus.PASS)


class GenerateArtifactCrossChapterTests(unittest.TestCase):
    def test_other_chapter_node_ids_passed_through_to_i3(self) -> None:
        built = build_small_clean_tree()
        other_ids = frozenset({NodeId("chap-08:root")})
        artifact = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=clean_registry(),
            other_chapter_node_ids=other_ids,
        )
        i3 = next(
            r for r in artifact.validation_metadata.validation_results if r.invariant_id.value == "I3"
        )
        self.assertEqual(i3.status, ValidationStatus.PASS)


if __name__ == "__main__":
    unittest.main()