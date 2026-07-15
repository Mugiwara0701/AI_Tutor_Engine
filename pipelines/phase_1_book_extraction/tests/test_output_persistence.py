"""
tests/test_output_persistence.py — Phase 1 Output Persistence Enhancement:
regression tests for the five chapter-scoped artifact types this
enhancement made durable (compiler/persistence.py, knowledge_graph/
persistence.py, dependency_graph/persistence.py, validation/persistence.py,
build_metadata/persistence.py) and their matching discovery.py modules.

Same FakeStorage double test_f2_artifact_manager.py already uses (in-memory
stand-in for OneDriveStorage exposing only upload_json/download_json/exists/
list_directory -- no Graph/MSAL/network involved), so these are pure unit
tests of the persistence/discovery surface itself, independent of
pipeline.py's own Stage A-E computation.

Per task instructions, these tests are generated only: they are not
executed here (same disclaimer tests/test_registries.py already carries),
because this sandbox has no network access to install this project's
runtime dependencies (fitz/PyMuPDF, pydantic, etc. -- see requirements.txt)
that modules/json_writer.py transitively imports. Every path, function
name, and exception type referenced below was read directly from the
persistence.py/discovery.py modules under test, not assumed.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import json_writer  # noqa: E402
from storage.exceptions import NotFoundError  # noqa: E402

from compiler.registry_manager import RegistryManager  # noqa: E402
from compiler import persistence as compiler_persistence  # noqa: E402
from compiler import discovery as compiler_discovery  # noqa: E402

from knowledge_graph.registries import GraphRegistryManager  # noqa: E402
from knowledge_graph.schema import KnowledgeGraphMetadata  # noqa: E402
from knowledge_graph import persistence as kg_persistence  # noqa: E402
from knowledge_graph import discovery as kg_discovery  # noqa: E402

from dependency_graph import persistence as dg_persistence  # noqa: E402
from dependency_graph import discovery as dg_discovery  # noqa: E402

from validation import persistence as validation_persistence  # noqa: E402
from validation import discovery as validation_discovery  # noqa: E402

from build_metadata import persistence as build_metadata_persistence  # noqa: E402
from build_metadata import discovery as build_metadata_discovery  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fake (mirrors tests/test_f2_artifact_manager.py's FakeStorage, but
# list_directory() here returns real file entries -- is_folder=False -- since
# every artifact type's discovery.py filters on that flag)
# ---------------------------------------------------------------------------

class FakeStorage:
    """In-memory stand-in for OneDriveStorage exposing only the surface
    persistence.py/discovery.py actually call: upload_json/download_json/
    exists/list_directory. No Graph/MSAL/network involved."""

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

    def list_directory(self, path=None):
        prefix = path.rstrip("/") + "/"
        matched = False
        out = []
        for p in self.files:
            if p.startswith(prefix) and "/" not in p[len(prefix):]:
                matched = True
                out.append({"name": p[len(prefix):], "is_folder": False, "size": 0, "path": p})
        if not matched:
            raise NotFoundError(path)
        return out


@pytest.fixture
def storage():
    return FakeStorage()


CHAPTER_KWARGS = dict(klass="Class_12", subject="Chemistry", book_slug="Book_One",
                       chapter_number=1, chapter_title="Solutions")


# ---------------------------------------------------------------------------
# Output directory structure (Step 4 / Step 7 "output directory structure")
# ---------------------------------------------------------------------------

class TestOutputDirectoryStructure:
    def test_artifact_types_cover_all_five_persisted_kinds(self):
        types = json_writer.artifact_types()
        for expected in ("registries", "knowledge_graph", "dependency_graph",
                          "validation", "compiler_metadata", "build_metadata"):
            assert expected in types

    def test_each_persistence_module_writes_under_its_own_subfolder(self):
        klass, subject, book_slug = "Class_12", "Chemistry", "Book_One"
        assert "/registries/" in compiler_persistence.registries_record_path(
            klass, subject, book_slug, 1, "Solutions")
        assert "/compiler_metadata/" in compiler_persistence.compiler_metadata_record_path(
            klass, subject, book_slug, 1, "Solutions")
        assert "/knowledge_graph/" in kg_persistence.knowledge_graph_record_path(
            klass, subject, book_slug, 1, "Solutions")
        assert "/dependency_graph/" in dg_persistence.dependency_graph_record_path(
            klass, subject, book_slug, 1, "Solutions")
        assert "/validation/" in validation_persistence.validation_record_path(
            klass, subject, book_slug, 1, "Solutions")
        assert "/build_metadata/" in build_metadata_persistence.build_metadata_record_path(
            klass, subject, book_slug, 1, "Solutions")

    def test_chapter_scoped_filename_matches_chapter_json_convention(self):
        """A chapter's persisted artifacts must be trivially correlatable
        with its Chapter JSON by filename (<NN>_<chapter-slug>.json)."""
        chapter_path = json_writer.chapter_output_path("Class_12", "Chemistry", "Book_One", 1, "Solutions")
        kg_path = kg_persistence.knowledge_graph_record_path("Class_12", "Chemistry", "Book_One", 1, "Solutions")
        assert os.path.basename(chapter_path) == os.path.basename(kg_path)


# ---------------------------------------------------------------------------
# Compiler IR: registries + compiler_metadata
# ---------------------------------------------------------------------------

class TestCompilerPersistence:
    def test_persist_and_load_registries_roundtrip(self, storage):
        registry_manager = RegistryManager()
        path = compiler_persistence.persist_registries(storage, registry_manager, **CHAPTER_KWARGS)
        assert storage.exists(path=path)
        loaded = compiler_persistence.load_registries(storage, **CHAPTER_KWARGS)
        assert loaded == registry_manager.serialize()

    def test_persist_and_load_compiler_metadata_roundtrip(self, storage):
        compiler_persistence.persist_compiler_metadata(
            storage, **CHAPTER_KWARGS,
            manifest={"m": 1}, statistics={"s": 1}, registry_fingerprints={"f": "abc"},
            compiler_fingerprint="abc123", validation_report={"ok": True},
            readiness_report={"ready": True}, build_summary={"done": True}, final_status="READY",
        )
        loaded = compiler_persistence.load_compiler_metadata(storage, **CHAPTER_KWARGS)
        assert loaded["final_status"] == "READY"
        assert loaded["compiler_fingerprint"] == "abc123"

    def test_load_registries_raises_not_found_when_never_persisted(self, storage):
        with pytest.raises(compiler_persistence.RegistryNotFoundError):
            compiler_persistence.load_registries(storage, **CHAPTER_KWARGS)

    def test_registries_exist_false_before_persist_true_after(self, storage):
        assert compiler_persistence.registries_exist(storage, **CHAPTER_KWARGS) is False
        compiler_persistence.persist_registries(storage, RegistryManager(), **CHAPTER_KWARGS)
        assert compiler_persistence.registries_exist(storage, **CHAPTER_KWARGS) is True

    def test_discovery_lists_persisted_compiler_metadata(self, storage):
        compiler_persistence.persist_compiler_metadata(
            storage, **CHAPTER_KWARGS,
            manifest={}, statistics={}, registry_fingerprints={}, compiler_fingerprint="x",
            validation_report={}, readiness_report={}, build_summary={}, final_status="READY",
        )
        names = compiler_discovery.list_compiler_metadata(
            storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json"]


# ---------------------------------------------------------------------------
# Knowledge Graph (Stage C)
# ---------------------------------------------------------------------------

class TestKnowledgeGraphPersistence:
    def _kwargs(self):
        return dict(
            metadata=KnowledgeGraphMetadata(graph_id="graph-ch1", graph_urn="urn:graph:ch1",
                                             source_chapter_identifier="ch1"),
            registry_manager=GraphRegistryManager(),
            manifest={"m": 1}, statistics={"s": 1}, validation_report={"ok": True},
            registry_fingerprints={"f": "abc"}, graph_fingerprint="fp123",
            readiness_report={"ready": True}, build_summary={"done": True}, final_status="READY",
        )

    def test_persist_and_load_roundtrip(self, storage):
        path = kg_persistence.persist_knowledge_graph(storage, **CHAPTER_KWARGS, **self._kwargs())
        assert storage.exists(path=path)
        loaded = kg_persistence.load_knowledge_graph(storage, **CHAPTER_KWARGS)
        assert loaded["graph_fingerprint"] == "fp123"
        assert loaded["final_status"] == "READY"
        assert "registries" in loaded and "metadata" in loaded

    def test_load_raises_not_found_when_never_persisted(self, storage):
        with pytest.raises(kg_persistence.KnowledgeGraphNotFoundError):
            kg_persistence.load_knowledge_graph(storage, **CHAPTER_KWARGS)

    def test_exists_reflects_persistence_state(self, storage):
        assert kg_persistence.knowledge_graph_exists(storage, **CHAPTER_KWARGS) is False
        kg_persistence.persist_knowledge_graph(storage, **CHAPTER_KWARGS, **self._kwargs())
        assert kg_persistence.knowledge_graph_exists(storage, **CHAPTER_KWARGS) is True

    def test_discovery_list_and_history(self, storage):
        kg_persistence.persist_knowledge_graph(storage, **CHAPTER_KWARGS, **self._kwargs())
        names = kg_discovery.list_knowledge_graphs(storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json"]
        history = kg_discovery.knowledge_graph_history(storage, "Class_12", "Chemistry", "Book_One")
        assert len(history) == 1
        assert history[0]["final_status"] == "READY"

    def test_discovery_returns_empty_list_when_folder_never_created(self, storage):
        assert kg_discovery.list_knowledge_graphs(storage, "Class_12", "Chemistry", "Nonexistent_Book") == []


# ---------------------------------------------------------------------------
# Dependency Graph (Phase E2)
# ---------------------------------------------------------------------------

class TestDependencyGraphPersistence:
    def test_persist_and_load_roundtrip(self, storage):
        graph_dict = {"metadata": {"chapter_id": "ch1"}, "nodes": [], "edges": []}
        path = dg_persistence.persist_dependency_graph(storage, graph_dict, **CHAPTER_KWARGS)
        assert storage.exists(path=path)
        loaded = dg_persistence.load_dependency_graph(storage, **CHAPTER_KWARGS)
        assert loaded == graph_dict

    def test_load_raises_not_found_when_never_persisted(self, storage):
        with pytest.raises(dg_persistence.DependencyGraphNotFoundError):
            dg_persistence.load_dependency_graph(storage, **CHAPTER_KWARGS)

    def test_discovery_lists_persisted_graphs(self, storage):
        dg_persistence.persist_dependency_graph(storage, {"nodes": [], "edges": []}, **CHAPTER_KWARGS)
        names = dg_discovery.list_dependency_graphs(storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json"]


# ---------------------------------------------------------------------------
# Validation record (Stage D1 + D2 + D3)
# ---------------------------------------------------------------------------

class TestValidationPersistence:
    def test_persist_and_load_roundtrip(self, storage):
        validation_persistence.persist_validation_record(
            storage, **CHAPTER_KWARGS,
            system_integrity_report={"ok": True}, determinism_report={"deterministic": True},
            release_readiness_report={"ready": True}, release_status="RELEASED",
        )
        loaded = validation_persistence.load_validation_record(storage, **CHAPTER_KWARGS)
        assert loaded["release_status"] == "RELEASED"
        assert loaded["determinism_report"] == {"deterministic": True}

    def test_load_raises_not_found_when_never_persisted(self, storage):
        with pytest.raises(validation_persistence.ValidationRecordNotFoundError):
            validation_persistence.load_validation_record(storage, **CHAPTER_KWARGS)

    def test_discovery_lists_persisted_records(self, storage):
        validation_persistence.persist_validation_record(
            storage, **CHAPTER_KWARGS, system_integrity_report={}, determinism_report={},
            release_readiness_report={}, release_status="RELEASED",
        )
        names = validation_discovery.list_validation_records(storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json"]


# ---------------------------------------------------------------------------
# Build Metadata (Phase E1)
# ---------------------------------------------------------------------------

class TestBuildMetadataPersistence:
    def test_persist_and_load_roundtrip(self, storage):
        build_metadata_persistence.persist_build_metadata(
            storage, {"build_id": "b1", "version": "1.0.0"}, **CHAPTER_KWARGS)
        loaded = build_metadata_persistence.load_build_metadata(storage, **CHAPTER_KWARGS)
        assert loaded == {"build_id": "b1", "version": "1.0.0"}

    def test_load_raises_not_found_when_never_persisted(self, storage):
        with pytest.raises(build_metadata_persistence.BuildMetadataNotFoundError):
            build_metadata_persistence.load_build_metadata(storage, **CHAPTER_KWARGS)

    def test_discovery_lists_persisted_records(self, storage):
        build_metadata_persistence.persist_build_metadata(storage, {"build_id": "b1"}, **CHAPTER_KWARGS)
        names = build_metadata_discovery.list_build_metadata(storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json"]


# ---------------------------------------------------------------------------
# Cross-cutting: independence between chapters and between artifact types
# ---------------------------------------------------------------------------

class TestArtifactIndependence:
    def test_two_chapters_in_same_book_persist_to_distinct_paths(self, storage):
        kwargs1 = dict(CHAPTER_KWARGS)
        kwargs2 = dict(CHAPTER_KWARGS, chapter_number=2, chapter_title="Electrochemistry")
        build_metadata_persistence.persist_build_metadata(storage, {"v": 1}, **kwargs1)
        build_metadata_persistence.persist_build_metadata(storage, {"v": 2}, **kwargs2)
        assert build_metadata_persistence.load_build_metadata(storage, **kwargs1) == {"v": 1}
        assert build_metadata_persistence.load_build_metadata(storage, **kwargs2) == {"v": 2}
        names = build_metadata_discovery.list_build_metadata(storage, "Class_12", "Chemistry", "Book_One")
        assert names == ["01_solutions.json", "02_electrochemistry.json"]

    def test_persisting_one_artifact_type_does_not_affect_another(self, storage):
        build_metadata_persistence.persist_build_metadata(storage, {"v": 1}, **CHAPTER_KWARGS)
        with pytest.raises(dg_persistence.DependencyGraphNotFoundError):
            dg_persistence.load_dependency_graph(storage, **CHAPTER_KWARGS)
        with pytest.raises(validation_persistence.ValidationRecordNotFoundError):
            validation_persistence.load_validation_record(storage, **CHAPTER_KWARGS)