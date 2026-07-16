"""document_structure_tree/tests/test_serialization.py — Milestone 4:
deterministic serialization/deserialization, round-trip support, the
schema §5.3 null-handling rules, the isolation principle, and a direct
conformance check against the frozen schema document's own §5.6
example instance (roadmap M9's own deliverables)."""
from __future__ import annotations

import json
import random
import unittest

from document_structure_tree import (
    DocumentStructureTree,
    HeadingDetectionEntry,
    HeadingDetectionMethod,
    HeadingNode,
    deserialize,
    generate_artifact,
    round_trip_text,
    serialize,
    to_canonical_json,
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

# The frozen schema document's own §5.6 "Example instance (illustrative,
# complete)" -- copied verbatim as a fixture, per roadmap M9's own
# acceptance criterion: "Deserialize the schema document's own §5.6
# example JSON directly ... and confirm it parses cleanly -- this is a
# direct conformance check against the frozen spec text itself."
SCHEMA_5_6_EXAMPLE = """
{
  "artifact_metadata": {
    "schema_version": "1.0.0",
    "compiler_version": "3.4.2",
    "identity_scheme_version": "1",
    "chapter_id": "chap-07",
    "build_timestamp": "2026-07-15T09:00:00Z",
    "chapter_fingerprint": "bf375dc8fa13158a756b4fa6e6dfb549c1e303900ef80ce8a3917ad9e968f478"
  },
  "build_provenance": {
    "canonical_registry_snapshot_ref": "registry-snap-2026-07-01"
  },
  "validation_metadata": {
    "validation_status": "pass",
    "validation_results": [
      { "invariant_id": "S1", "status": "pass" },
      { "invariant_id": "S2", "status": "pass" },
      { "invariant_id": "S3", "status": "pass" },
      { "invariant_id": "S4", "status": "pass" },
      { "invariant_id": "R1", "status": "pass" },
      { "invariant_id": "R2", "status": "pass" },
      { "invariant_id": "R3", "status": "pass" },
      { "invariant_id": "R4", "status": "pass" },
      { "invariant_id": "O1", "status": "pass" },
      { "invariant_id": "O2", "status": "pass" },
      { "invariant_id": "I1", "status": "pass" },
      { "invariant_id": "I2", "status": "pass" },
      { "invariant_id": "I3", "status": "pass" },
      { "invariant_id": "B1", "status": "pass" },
      { "invariant_id": "B2", "status": "pass" },
      { "invariant_id": "B3", "status": "pass" }
    ]
  },
  "tree": [
    {
      "node_id": "chap-07:root",
      "chapter_id": "chap-07",
      "level": 0,
      "parent_id": null,
      "sequence": [
        { "entry_type": "content", "ref": "obj-441", "object_type": "paragraph_group" },
        { "entry_type": "heading", "ref": "chap-07:4.1" }
      ],
      "span": {
        "block_range": { "start": 0, "end": 88 }
      }
    },
    {
      "node_id": "chap-07:4.1",
      "chapter_id": "chap-07",
      "level": 1,
      "parent_id": "chap-07:root",
      "number": "4.1",
      "title": "Newton's Second Law",
      "sequence": [
        { "entry_type": "content", "ref": "obj-442", "object_type": "definition" }
      ],
      "span": {
        "block_range": { "start": 3, "end": 40 },
        "page_range": { "start": "88", "end": "94" }
      }
    }
  ]
}
"""


def _generate(**overrides):
    built = build_small_clean_tree()
    kwargs = dict(
        tree=built.tree,
        chapter_id=CHAPTER_ID,
        schema_version=SCHEMA_VERSION,
        compiler_version=COMPILER_VERSION,
        canonical_registry_snapshot_ref=REGISTRY_REF,
        build_timestamp=BUILD_TIMESTAMP,
        registry=clean_registry(),
    )
    kwargs.update(overrides)
    return generate_artifact(**kwargs)


class SchemaExampleConformanceTests(unittest.TestCase):
    """The one direct conformance check against the frozen spec text
    itself, not just against this implementation's own round-trip
    (roadmap M9)."""

    def test_schema_5_6_example_parses_cleanly(self) -> None:
        data = json.loads(SCHEMA_5_6_EXAMPLE)
        dst = DocumentStructureTree.from_json(data)
        self.assertEqual(dst.artifact_metadata.chapter_id.value, "chap-07")
        self.assertEqual(len(dst.tree), 2)

    def test_schema_5_6_example_round_trips(self) -> None:
        data = json.loads(SCHEMA_5_6_EXAMPLE)
        dst = DocumentStructureTree.from_json(data)
        text_once, decoded, text_twice = round_trip_text(dst)
        self.assertEqual(text_once, text_twice)
        self.assertEqual(to_canonical_json(decoded), to_canonical_json(dst))


class DeterministicSerializationTests(unittest.TestCase):
    def test_serializing_twice_is_byte_identical(self) -> None:
        artifact = _generate()
        self.assertEqual(serialize(artifact), serialize(artifact))

    def test_tree_array_order_does_not_affect_serialized_output(self) -> None:
        """Schema §5.2: 'Array order within tree carries no meaning' --
        proven here by shuffling the in-memory tree order before
        serializing and confirming byte-identical output either way."""
        artifact = _generate()
        shuffled_tree = list(artifact.tree)
        random.Random(1234).shuffle(shuffled_tree)
        shuffled_artifact = DocumentStructureTree(
            artifact_metadata=artifact.artifact_metadata,
            build_provenance=artifact.build_provenance,
            validation_metadata=artifact.validation_metadata,
            tree=tuple(shuffled_tree),
            derived_summary=artifact.derived_summary,
        )
        self.assertEqual(serialize(artifact), serialize(shuffled_artifact))

    def test_round_trip_recovers_equivalent_artifact(self) -> None:
        artifact = _generate()
        text_once, decoded, text_twice = round_trip_text(artifact)
        self.assertEqual(text_once, text_twice)
        # Compare via canonical JSON, not Python `==`: `tree`'s array
        # order carries no meaning (schema §5.2), so two artifacts
        # that are equal in every schema-defined field may still
        # legitimately differ in raw tuple order and therefore in
        # dataclass `==`; canonical-JSON equality is the semantically
        # correct notion of "recovers an equal value" here.
        self.assertEqual(to_canonical_json(decoded), to_canonical_json(artifact))
        self.assertEqual(len(decoded.tree), len(artifact.tree))

    def test_isolation_principle_tree_alone_remains_interpretable(self) -> None:
        """Architecture §9 / schema §2.2: 'tree must remain fully
        interpretable with the other layers stripped.' Strips
        `artifact_metadata`/`build_provenance`/`validation_metadata`
        from a serialized artifact and confirms `tree` alone still
        deserializes and supports node lookup and children/content
        projection."""
        artifact = _generate()
        full = json.loads(serialize(artifact))
        tree_only = full["tree"]

        nodes = [HeadingNode.from_json(n) for n in tree_only]
        self.assertEqual(len(nodes), len(artifact.tree))

        by_id = {n.node_id: n for n in nodes}
        root = next(n for n in nodes if n.level.value == 0)
        # Children/content projections still work from `tree` alone.
        for child_id in root.children:
            self.assertIn(child_id, by_id)
        self.assertTrue(all(isinstance(entry.ref.value, str) for entry in root.content))


class NullHandlingTests(unittest.TestCase):
    """One dedicated test per schema §5.3 bullet."""

    def setUp(self) -> None:
        self.artifact = _generate()
        self.doc = json.loads(serialize(self.artifact))

    def test_root_parent_id_is_explicit_null(self) -> None:
        root = next(n for n in self.doc["tree"] if n["level"] == 0)
        self.assertIn("parent_id", root)
        self.assertIsNone(root["parent_id"])

    def test_non_root_parent_id_present_as_string(self) -> None:
        non_root = next(n for n in self.doc["tree"] if n["level"] != 0)
        self.assertIsInstance(non_root["parent_id"], str)

    def test_number_and_title_omitted_when_absent_not_null(self) -> None:
        root = next(n for n in self.doc["tree"] if n["level"] == 0)
        self.assertNotIn("number", root)
        self.assertNotIn("title", root)

    def test_span_sub_fields_independently_omitted(self) -> None:
        # This baseline's builder (Milestone 2.2) leaves every span
        # empty pending span computation (roadmap M3) -- both
        # sub-fields are omitted for every node, which is itself the
        # schema §13 "empty span" case, not a defect.
        for node in self.doc["tree"]:
            self.assertNotIn("block_range", node["span"])
            self.assertNotIn("page_range", node["span"])

    def test_object_type_omitted_iff_heading_entry(self) -> None:
        for node in self.doc["tree"]:
            for entry in node["sequence"]:
                if entry["entry_type"] == "heading":
                    self.assertNotIn("object_type", entry)
                else:
                    self.assertIn("object_type", entry)

    def test_heading_detection_provenance_omitted_when_not_produced(self) -> None:
        self.assertNotIn("heading_detection_provenance", self.doc["build_provenance"])

    def test_heading_detection_provenance_present_when_produced(self) -> None:
        built = build_small_clean_tree()
        entry = HeadingDetectionEntry(node_id=built.root.node_id, method=HeadingDetectionMethod.TOC_MATCHING)
        artifact = _generate(tree=built.tree, heading_detection_provenance=(entry,))
        doc = json.loads(serialize(artifact))
        self.assertIn("heading_detection_provenance", doc["build_provenance"])

    def test_derived_summary_omitted_when_not_produced(self) -> None:
        artifact = _generate(include_derived_summary=False)
        doc = json.loads(serialize(artifact))
        self.assertNotIn("derived_summary", doc)

    def test_derived_summary_present_when_produced(self) -> None:
        self.assertIn("derived_summary", self.doc)

    def test_violations_omitted_when_passing(self) -> None:
        for result in self.doc["validation_metadata"]["validation_results"]:
            if result["status"] == "pass":
                self.assertNotIn("violations", result)

    def test_violations_present_and_non_empty_when_failing(self) -> None:
        # No registry -> R2/R3/R4/B2 fail with explicit violations.
        failing_artifact = _generate(registry=None)
        doc = json.loads(serialize(failing_artifact))
        saw_a_failure = False
        for result in doc["validation_metadata"]["validation_results"]:
            if result["status"] == "fail":
                saw_a_failure = True
                self.assertIn("violations", result)
                self.assertGreater(len(result["violations"]), 0)
        self.assertTrue(saw_a_failure)


class DeserializeErrorHandlingTests(unittest.TestCase):
    def test_malformed_json_text_raises_serialization_error(self) -> None:
        from document_structure_tree import DSTSerializationError

        with self.assertRaises(DSTSerializationError):
            deserialize("{not valid json")


if __name__ == "__main__":
    unittest.main()