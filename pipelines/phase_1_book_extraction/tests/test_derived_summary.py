"""document_structure_tree/tests/test_derived_summary.py — Milestone 4:
`compute_derived_summary()` (schema §2.10, roadmap M11)."""
from __future__ import annotations

import unittest

from document_structure_tree import DerivedSummary, compute_derived_summary, generate_artifact

from .fixtures import (
    BUILD_TIMESTAMP,
    CHAPTER_ID,
    COMPILER_VERSION,
    REGISTRY_REF,
    SCHEMA_VERSION,
    build_small_clean_tree,
    clean_registry,
)


class ComputeDerivedSummaryTests(unittest.TestCase):
    def test_empty_tree_is_well_defined(self) -> None:
        summary = compute_derived_summary(())
        self.assertIsInstance(summary, DerivedSummary)
        self.assertEqual(summary.data["node_count"], 0)
        self.assertEqual(summary.data["max_depth"], 0)
        self.assertEqual(summary.data["leaf_node_count"], 0)

    def test_counts_against_hand_computed_fixture(self) -> None:
        built = build_small_clean_tree()
        summary = compute_derived_summary(built.tree)

        # root + h1 + h2 + h1a = 4 nodes.
        self.assertEqual(summary.data["node_count"], 4)
        # root=0, h1/h2=1, h1a=2 -> max depth 2.
        self.assertEqual(summary.data["max_depth"], 2)
        # leaves: h2 (no children, no descendants) and h1a (leaf heading).
        self.assertEqual(summary.data["leaf_node_count"], 2)
        # every non-root heading in this fixture is numbered.
        self.assertEqual(summary.data["numbered_heading_count"], 3)
        self.assertEqual(summary.data["unnumbered_heading_count"], 0)
        # every non-root heading in this fixture carries a title.
        self.assertEqual(summary.data["nodes_with_title"], 3)
        # two content refs total (root-owned + h1a-owned).
        self.assertEqual(summary.data["content_sequence_entry_count"], 2)
        # two heading-type sequence entries: root->h1, root->h2, h1->h1a = 3.
        self.assertEqual(summary.data["heading_sequence_entry_count"], 3)
        # span computation (roadmap M3) is not yet implemented (Milestone
        # 2.2's builder leaves every span empty) -- both counts are 0,
        # which is itself a meaningful, correctly-reported fact, not a
        # missing feature of this milestone.
        self.assertEqual(summary.data["nodes_with_block_range"], 0)
        self.assertEqual(summary.data["nodes_with_page_range"], 0)

    def test_never_referenced_by_validation_or_required_for_safety(self) -> None:
        """Roadmap M11's own acceptance criterion: removing
        `derived_summary` entirely from an artifact must not change
        `validation_status` or break deserialization of any other
        layer (schema §2.10, §9.5)."""
        built = build_small_clean_tree()
        registry = clean_registry()

        with_summary = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=registry,
            include_derived_summary=True,
        )
        without_summary = generate_artifact(
            tree=built.tree,
            chapter_id=CHAPTER_ID,
            schema_version=SCHEMA_VERSION,
            compiler_version=COMPILER_VERSION,
            canonical_registry_snapshot_ref=REGISTRY_REF,
            build_timestamp=BUILD_TIMESTAMP,
            registry=registry,
            include_derived_summary=False,
        )

        self.assertIsNotNone(with_summary.derived_summary)
        self.assertIsNone(without_summary.derived_summary)
        self.assertEqual(
            with_summary.validation_metadata.validation_status,
            without_summary.validation_metadata.validation_status,
        )
        self.assertEqual(
            with_summary.validation_metadata.validation_results,
            without_summary.validation_metadata.validation_results,
        )
        # Every other layer still deserializes fine either way.
        self.assertNotIn("derived_summary", without_summary.to_json())
        self.assertIn("derived_summary", with_summary.to_json())


if __name__ == "__main__":
    unittest.main()