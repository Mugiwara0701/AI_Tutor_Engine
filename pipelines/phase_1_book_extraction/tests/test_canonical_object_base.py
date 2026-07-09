"""
Unit tests for A1.1 -- schemas.canonical_base.CanonicalObjectBase.

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from schemas.canonical_base import (
    CanonicalObjectBase,
    Provenance,
    CreationMetadata,
)


# --------------------------------------------------------------------------
# Object creation
# --------------------------------------------------------------------------
class TestObjectCreation:
    def test_minimal_required_fields(self):
        obj = CanonicalObjectBase(id="obj-1", object_type="concept")
        assert obj.id == "obj-1"
        assert obj.object_type == "concept"

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            CanonicalObjectBase(object_type="concept")

    def test_missing_object_type_raises(self):
        with pytest.raises(ValidationError):
            CanonicalObjectBase(id="obj-1")

    def test_full_fields_creation(self):
        obj = CanonicalObjectBase(
            id="obj-2",
            urn="urn:book:ch1:concept:obj-2",
            object_type="figure",
            schema_version="1.1.0",
            compiler_version="0.9.0",
            subject="physics",
            chapter_reference="chapter-3",
            topic_ids=["topic-1", "topic-2"],
            concept_ids=["concept-1"],
            provenance=Provenance(source="pdf", stage="stage_d", page=12),
            extraction_confidence=0.87,
            validation_status="validated",
            duplicate_lineage=[{"merged_from": "obj-old"}],
            creation_metadata=CreationMetadata(created_by="pipeline"),
        )
        assert obj.urn == "urn:book:ch1:concept:obj-2"
        assert obj.subject == "physics"
        assert obj.topic_ids == ["topic-1", "topic-2"]
        assert obj.extraction_confidence == 0.87
        assert obj.validation_status == "validated"
        assert obj.duplicate_lineage == [{"merged_from": "obj-old"}]
        assert obj.provenance.stage == "stage_d"
        assert obj.creation_metadata.created_by == "pipeline"


# --------------------------------------------------------------------------
# Default values
# --------------------------------------------------------------------------
class TestDefaultValues:
    def test_defaults_when_only_required_fields_given(self):
        obj = CanonicalObjectBase(id="obj-3", object_type="table")
        assert obj.urn is None
        assert obj.schema_version == "1.0.0"
        assert obj.compiler_version is None
        assert obj.subject is None
        assert obj.chapter_reference is None
        assert obj.topic_ids == []
        assert obj.concept_ids == []
        assert obj.extraction_confidence == 0.0
        assert obj.validation_status == "unvalidated"
        assert obj.duplicate_lineage == []
        assert isinstance(obj.provenance, Provenance)
        assert isinstance(obj.creation_metadata, CreationMetadata)

    def test_default_lists_are_independent_instances(self):
        obj_a = CanonicalObjectBase(id="a", object_type="concept")
        obj_b = CanonicalObjectBase(id="b", object_type="concept")
        obj_a.topic_ids.append("shared-topic")
        assert obj_a.topic_ids == ["shared-topic"]
        assert obj_b.topic_ids == []  # no shared mutable default

    def test_provenance_defaults(self):
        prov = Provenance()
        assert prov.source is None
        assert prov.stage is None
        assert prov.extractor is None
        assert prov.page is None

    def test_creation_metadata_defaults(self):
        meta = CreationMetadata()
        assert meta.created_at is None
        assert meta.created_by is None
        assert meta.run_id is None


# --------------------------------------------------------------------------
# Optional fields
# --------------------------------------------------------------------------
class TestOptionalFields:
    def test_optional_fields_accept_none_explicitly(self):
        obj = CanonicalObjectBase(
            id="obj-4",
            object_type="equation",
            urn=None,
            compiler_version=None,
            subject=None,
            chapter_reference=None,
        )
        assert obj.urn is None
        assert obj.compiler_version is None

    def test_extra_fields_allowed_extra_allow(self):
        # extra="allow" so a subclass or forward-compatible payload with
        # additional keys does not fail validation.
        obj = CanonicalObjectBase(
            id="obj-5",
            object_type="activity",
            some_future_field="value",
        )
        assert obj.model_dump()["some_future_field"] == "value"


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------
class TestInheritance:
    def test_subclass_can_add_fields(self):
        class CanonicalConcept(CanonicalObjectBase):
            name: str
            aliases: list[str] = []

        concept = CanonicalConcept(
            id="concept-1",
            object_type="concept",
            name="Newton's First Law",
        )
        assert isinstance(concept, CanonicalObjectBase)
        assert concept.name == "Newton's First Law"
        assert concept.aliases == []
        # Inherited defaults still apply.
        assert concept.validation_status == "unvalidated"
        assert concept.schema_version == "1.0.0"

    def test_subclass_inherits_required_base_fields(self):
        class CanonicalFigure(CanonicalObjectBase):
            caption: str = ""

        with pytest.raises(ValidationError):
            # still must supply id/object_type from the base
            CanonicalFigure(caption="a caption")

    def test_subclass_can_override_defaults(self):
        class CanonicalValidatedObject(CanonicalObjectBase):
            validation_status: str = "validated"

        obj = CanonicalValidatedObject(id="obj-6", object_type="table")
        assert obj.validation_status == "validated"

    def test_is_instance_of_base_model(self):
        obj = CanonicalObjectBase(id="obj-7", object_type="box")
        assert isinstance(obj, BaseModel)
        assert isinstance(obj, CanonicalObjectBase)


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------
class TestSerialization:
    def test_model_dump_round_trip(self):
        obj = CanonicalObjectBase(
            id="obj-8",
            object_type="diagram",
            subject="biology",
            topic_ids=["topic-9"],
        )
        dumped = obj.model_dump()
        rebuilt = CanonicalObjectBase(**dumped)
        assert rebuilt == obj

    def test_model_dump_json_round_trip(self):
        obj = CanonicalObjectBase(
            id="obj-9",
            object_type="chart",
            provenance=Provenance(source="ocr", page=4),
        )
        json_str = obj.model_dump_json()
        rebuilt = CanonicalObjectBase.model_validate_json(json_str)
        assert rebuilt == obj
        assert rebuilt.provenance.page == 4

    def test_nested_models_serialize_as_dicts(self):
        obj = CanonicalObjectBase(id="obj-10", object_type="map")
        dumped = obj.model_dump()
        assert isinstance(dumped["provenance"], dict)
        assert isinstance(dumped["creation_metadata"], dict)
        assert isinstance(dumped["duplicate_lineage"], list)

    def test_duplicate_lineage_shape_matches_educational_object(self):
        # Mirrors EducationalObject.duplicate_lineage in chapter_schema.py
        # (List[Dict[str, Any]]) so a future migration is a no-op here.
        obj = CanonicalObjectBase(
            id="obj-11",
            object_type="equation",
            duplicate_lineage=[{"reason": "duplicate_formula", "of": "obj-old"}],
        )
        dumped = obj.model_dump()
        assert dumped["duplicate_lineage"] == [
            {"reason": "duplicate_formula", "of": "obj-old"}
        ]


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_existing_chapter_schema_imports_untouched(self):
        # A1.1 must not break any existing schema import.
        from schemas import (
            ChapterJSON, BBox, ExtractionMetadata, DocumentInfo,
            ChapterMetadata, ChapterStatistics, PageInfo, TopicNode,
            Concept, Definition, Example, Activity, Figure, Table,
            Equation, Diagram, Chart, Graph, Map, Timeline, Box,
            NoteItem, WarningItem, GraphEdge, LearningGraph, ConceptGraph,
            SemanticIndexEntry, AIMetadata, GenerationMetadata,
            QualityScores, ExtractionLogs,
        )
        assert ChapterJSON is not None
        assert Concept is not None

    def test_chapter_json_still_constructs_with_defaults(self):
        from schemas import ChapterJSON

        chapter = ChapterJSON()
        assert chapter.schema_version == "2.0.0"
        assert chapter.topics == []
        assert chapter.concepts == []

    def test_educational_object_duplicate_lineage_unaffected(self):
        from schemas.chapter_schema import EducationalObject

        eo = EducationalObject(
            id="eo-1",
            block_id="block-1",
            block_type="Ambiguous",
            priority="medium",
            educational_object_type="concept",
            duplicate_lineage=[{"of": "eo-old"}],
        )
        assert eo.duplicate_lineage == [{"of": "eo-old"}]

    def test_canonical_object_base_is_new_addition_not_a_replacement(self):
        # CanonicalObjectBase is importable alongside existing schemas
        # without altering their behavior (no shared base yet).
        from schemas import CanonicalObjectBase
        from schemas.chapter_schema import Concept

        assert not issubclass(Concept, CanonicalObjectBase)

    def test_educational_objects_schema_module_untouched(self):
        from schemas.educational_objects_schema import (
            EducationalObjectsDocument,
        )

        doc = EducationalObjectsDocument()
        assert doc.schema_version == "2.0.0"
        assert doc.phase == "phase_1_educational_extraction"