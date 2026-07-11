"""
tests/test_e2_dependency_graph.py — unit tests for Phase E2: Build
Dependency Graph (dependency_graph/), and its pipeline.py /
dependency_graph.state integration.

This file does NOT re-test Compiler IR construction/validation/
fingerprinting/finalization, Knowledge Graph construction/validation/
fingerprinting/finalization, System Integrity, Determinism, Release
Readiness, or Build Metadata directly -- it treats all of those as
frozen, already-tested dependencies (see tests/test_e1_build_metadata.py,
which this file's own `build_full_pipeline_state()` helper extends by
one more phase, following that file's own "duplicated here, not
imported" convention -- this repo has no tests/__init__.py, so tests/
is not a package).
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

from compiler.registries import (
    REGISTRY_NAMES,
    create_registry_manager,
    populate_registries,
)
from compiler.registry_manager import RegistryManager
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.validation import validate_compiler_state
from compiler.build import generate_compiler_manifest, generate_compiler_statistics
from compiler.fingerprints import generate_compiler_fingerprints
from compiler.finalize import finalize_compiler_build

from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.validation import validate_knowledge_graph
from knowledge_graph.build import (
    generate_knowledge_graph_manifest,
    generate_knowledge_graph_statistics,
)
from knowledge_graph.identity import (
    graph_id as expected_kg_graph_id,
    graph_urn as expected_kg_graph_urn,
)
from knowledge_graph.schema import KnowledgeGraphMetadata
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph
from knowledge_graph.registries import (
    NODE_REGISTRY_NAME as KG_NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME as KG_EDGE_REGISTRY_NAME,
)

from validation.system_integrity import validate_system_integrity
from validation.determinism import validate_determinism
from validation.release import finalize_release

from build_metadata.build import finalize_build_metadata

from dependency_graph.build import (
    DEPENDENCY_GRAPH_VERSION,
    KNOWLEDGE_GRAPH_REGISTRY_ROLES,
    generate_dependency_graph,
)
from dependency_graph.edge import DependencyEdge, DEPENDENCY_EDGE_TYPES
from dependency_graph.exceptions import UnknownDependencyRegistryError
from dependency_graph.identity import (
    graph_id as expected_dg_graph_id,
    graph_urn as expected_dg_graph_urn,
    node_id as expected_dg_node_id,
)
from dependency_graph.node import DependencyNode, DEPENDENCY_NODE_TYPES
from dependency_graph.registries import (
    DEPENDENCY_REGISTRY_NAMES,
    NODE_REGISTRY_NAME as DG_NODE_REGISTRY_NAME,
    EDGE_REGISTRY_NAME as DG_EDGE_REGISTRY_NAME,
    create_dependency_registry_manager,
    get_dependency_registry,
)
from dependency_graph import state as dependency_graph_state

NAMESPACE = "physics:chapter-3"


# --------------------------------------------------------------------------
# Helpers -- full Phase B->E1 pipeline fixture (same shape
# tests/test_e1_build_metadata.py's own build_full_pipeline_state()
# already establishes, extended one phase and duplicated here, not
# imported).
# --------------------------------------------------------------------------

def make_item(id_, urn, object_type, *, label_key=None, label_value=None,
              source_page=1, compiler_version="B5.1", **extra):
    d = {
        "id": id_,
        "urn": urn,
        "object_type": object_type,
        "provenance": {
            "source_page": source_page,
            "source_block_id": None,
            "extraction_method": "deterministic",
            "confidence": 0.9,
        },
        "creation_metadata": {
            "created_at": "2026-01-01T00:00:00+00:00",
            "compiler_version": compiler_version,
            "generator": None,
        },
    }
    if label_key is not None:
        d[label_key] = label_value
    d.update(extra)
    return d


def make_relationship_ready_manager() -> RegistryManager:
    topic = make_item(
        "t1", "urn:t:t1", "topic", label_key="title", label_value="Motion",
        concepts=["c1"],
    )
    concept = make_item(
        "c1", "urn:c:c1", "concept", label_key="name", label_value="Force",
        topic_ids=["t1"],
    )
    definition = make_item(
        "d1", "urn:d:d1", "definition", label_key="term", label_value="Force",
        topic_ids=["t1"],
    )
    manager = create_registry_manager()
    populate_registries(manager, topics=[topic], concepts=[concept], definitions=[definition])
    resolve_references(manager)
    resolve_relationships(manager)
    return manager


def build_full_pipeline_state(*, namespace=NAMESPACE):
    """One-shot: Phase B -> Phase C -> Phase D1 -> Phase D2 -> Phase D3
    -> Phase E1, exactly the sequence pipeline.py runs immediately
    before its own Phase E2 integration point. Returns a dict of every
    artifact generate_dependency_graph() consumes, keyed the same way
    that function's own parameter names read."""
    manager = make_relationship_ready_manager()
    compiler_validation_report = validate_compiler_state(
        manager, topics=[manager.get("topics").get_by_id("t1")],
    )
    compiler_manifest = generate_compiler_manifest(
        manager, compiler_validation_report, chapter_identifier=namespace,
    )
    compiler_statistics = generate_compiler_statistics(manager, compiler_validation_report)
    compiler_fp_results = generate_compiler_fingerprints(
        manager, manifest=compiler_manifest, statistics=compiler_statistics,
        validation_report=compiler_validation_report,
    )
    compiler_finalization = finalize_compiler_build(
        manager,
        validation_report=compiler_validation_report,
        manifest=compiler_manifest,
        statistics=compiler_statistics,
        registry_fingerprints=compiler_fp_results["registry_fingerprints"],
        compiler_fingerprint=compiler_fp_results["compiler_fingerprint"],
        readiness_report=compiler_fp_results["readiness_report"],
    )

    graph_manager = build_knowledge_graph_nodes(manager, graph_namespace=namespace)
    graph_manager = build_knowledge_graph_edges(
        manager, graph_manager, graph_namespace=namespace,
    )
    kg_validation_report = validate_knowledge_graph(
        graph_manager, compiler_registry_manager=manager,
    )
    graph_metadata_obj = KnowledgeGraphMetadata(
        graph_id=expected_kg_graph_id(namespace),
        graph_urn=expected_kg_graph_urn(namespace),
        source_chapter_identifier=namespace,
        source_compiler_version=compiler_manifest.get("compiler_version"),
    )
    kg_manifest = generate_knowledge_graph_manifest(
        graph_manager, kg_validation_report, graph_metadata_obj,
    )
    kg_statistics = generate_knowledge_graph_statistics(graph_manager, kg_validation_report)
    kg_fp_results = generate_graph_fingerprints(
        graph_manager, manifest=kg_manifest, statistics=kg_statistics,
        validation_report=kg_validation_report,
    )
    kg_finalization = finalize_knowledge_graph(
        graph_manager,
        validation_report=kg_validation_report,
        manifest=kg_manifest,
        statistics=kg_statistics,
        registry_fingerprints=kg_fp_results["registry_fingerprints"],
        graph_fingerprint=kg_fp_results["graph_fingerprint"],
        readiness_report=kg_fp_results["readiness_report"],
    )

    state = {
        "compiler_registry_manager": manager,
        "compiler_manifest": compiler_manifest,
        "compiler_statistics": compiler_statistics,
        "compiler_registry_fingerprints": compiler_fp_results["registry_fingerprints"],
        "compiler_fingerprint": compiler_fp_results["compiler_fingerprint"],
        "compiler_readiness_report": compiler_fp_results["readiness_report"],
        "compiler_build_summary": compiler_finalization["build_summary"],
        "final_compiler_status": compiler_finalization["final_status"],
        "graph_registry_manager": graph_manager,
        "knowledge_graph_manifest": kg_manifest,
        "knowledge_graph_statistics": kg_statistics,
        "knowledge_graph_registry_fingerprints": kg_fp_results["registry_fingerprints"],
        "knowledge_graph_fingerprint": kg_fp_results["graph_fingerprint"],
        "knowledge_graph_readiness_report": kg_fp_results["readiness_report"],
        "knowledge_graph_build_summary": kg_finalization["graph_build_summary"],
        "final_graph_status": kg_finalization["graph_final_status"],
    }
    state["system_integrity_report"] = validate_system_integrity(
        state["compiler_registry_manager"], state["graph_registry_manager"],
        compiler_validation_report=compiler_validation_report,
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_validation_report=kg_validation_report,
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
    )
    state["determinism_report"] = validate_determinism(
        state["compiler_registry_manager"], state["graph_registry_manager"],
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        system_integrity_report=state["system_integrity_report"],
    )
    release_finalization = finalize_release(
        compiler_validation_report=compiler_validation_report,
        knowledge_graph_validation_report=kg_validation_report,
        compiler_readiness_report=state["compiler_readiness_report"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        system_integrity_report=state["system_integrity_report"],
        determinism_report=state["determinism_report"],
        compiler_manifest=state["compiler_manifest"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        compiler_fingerprint=state["compiler_fingerprint"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        compiler_statistics=state["compiler_statistics"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
    )
    state["release_readiness_report"] = release_finalization["release_readiness_report"]
    state["release_status"] = release_finalization["release_status"]

    build_metadata_result = finalize_build_metadata(
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_fingerprint=state["compiler_fingerprint"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        final_compiler_status=state["final_compiler_status"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_fingerprint=state["knowledge_graph_fingerprint"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        final_graph_status=state["final_graph_status"],
        release_status=state["release_status"],
        pdf_path=None,
        compilation_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        compilation_end=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        use_vlm=True,
        page_batch_size=6,
        force=False,
    )
    state["build_metadata"] = build_metadata_result["build_metadata"]
    return state


def run_generate_dependency_graph(state: dict, *, namespace=NAMESPACE, **overrides) -> dict:
    """Calls generate_dependency_graph() with every artifact
    build_full_pipeline_state() produced, keyword-mapped onto that
    function's own parameter names -- exactly pipeline.py's own Phase
    E2 integration-point call shape."""
    kwargs = dict(
        namespace=namespace,
        compiler_manifest=state["compiler_manifest"],
        compiler_statistics=state["compiler_statistics"],
        compiler_registry_fingerprints=state["compiler_registry_fingerprints"],
        compiler_readiness_report=state["compiler_readiness_report"],
        compiler_build_summary=state["compiler_build_summary"],
        knowledge_graph_manifest=state["knowledge_graph_manifest"],
        knowledge_graph_statistics=state["knowledge_graph_statistics"],
        knowledge_graph_registry_fingerprints=state["knowledge_graph_registry_fingerprints"],
        knowledge_graph_readiness_report=state["knowledge_graph_readiness_report"],
        knowledge_graph_build_summary=state["knowledge_graph_build_summary"],
        release_readiness_report=state["release_readiness_report"],
        build_metadata=state["build_metadata"],
    )
    kwargs.update(overrides)
    return generate_dependency_graph(**kwargs)


def _all_none_kwargs(namespace=NAMESPACE) -> dict:
    return dict(
        namespace=namespace,
        compiler_manifest=None,
        compiler_statistics=None,
        compiler_registry_fingerprints=None,
        compiler_readiness_report=None,
        compiler_build_summary=None,
        knowledge_graph_manifest=None,
        knowledge_graph_statistics=None,
        knowledge_graph_registry_fingerprints=None,
        knowledge_graph_readiness_report=None,
        knowledge_graph_build_summary=None,
        release_readiness_report=None,
        build_metadata=None,
    )


@pytest.fixture(autouse=True)
def _reset_dependency_graph_state():
    """Every test starts and ends with a clean dependency_graph.state
    module -- mirrors tests/test_e1_build_metadata.py's own
    _reset_build_metadata_state fixture, one phase over."""
    dependency_graph_state.reset_dependency_graph_state()
    yield
    dependency_graph_state.reset_dependency_graph_state()


# --------------------------------------------------------------------------
# 1. Dependency Node
# --------------------------------------------------------------------------

class TestDependencyNode:
    def test_to_dict_round_trips_every_field(self):
        node = DependencyNode(
            node_id="dgnode:compiler_manifest:compiler_manifest",
            node_urn="urn:ncert-kg:dg:ns:node:compiler_manifest:compiler_manifest",
            node_type="compiler_manifest",
            artifact_key="compiler_manifest",
            graph_id="dg-ns",
            graph_urn="urn:ncert-kg:dg:ns",
            display_name="compiler_manifest",
        )
        d = node.to_dict()
        assert d["node_id"] == node.node_id
        assert d["node_type"] == "compiler_manifest"
        assert d["metadata"] == {}

    def test_node_type_is_from_the_closed_set(self):
        for node_type in DEPENDENCY_NODE_TYPES:
            assert isinstance(node_type, str) and node_type


# --------------------------------------------------------------------------
# 2. Dependency Edge
# --------------------------------------------------------------------------

class TestDependencyEdge:
    def test_to_dict_round_trips_every_field(self):
        edge = DependencyEdge(
            edge_id="dgedge:depends_on:a:b",
            edge_urn="urn:ncert-kg:dg:ns:edge:depends_on:a:b",
            edge_type="depends_on",
            source_node_id="a",
            target_node_id="b",
            graph_id="dg-ns",
            graph_urn="urn:ncert-kg:dg:ns",
        )
        d = edge.to_dict()
        assert d["source_node_id"] == "a"
        assert d["target_node_id"] == "b"
        assert d["directed"] is True

    def test_only_one_edge_type_exists(self):
        assert DEPENDENCY_EDGE_TYPES == ("depends_on",)


# --------------------------------------------------------------------------
# 3. Dependency Registry
# --------------------------------------------------------------------------

class TestDependencyRegistry:
    def test_create_dependency_registry_manager_starts_empty(self):
        manager = create_dependency_registry_manager()
        assert sorted(manager.names()) == sorted(DEPENDENCY_REGISTRY_NAMES)
        assert manager.get(DG_NODE_REGISTRY_NAME).size() == 0
        assert manager.get(DG_EDGE_REGISTRY_NAME).size() == 0

    def test_get_dependency_registry_rejects_unknown_role(self):
        manager = create_dependency_registry_manager()
        with pytest.raises(UnknownDependencyRegistryError):
            get_dependency_registry(manager, "not-a-real-role")

    def test_get_dependency_registry_returns_known_roles(self):
        manager = create_dependency_registry_manager()
        assert get_dependency_registry(manager, DG_NODE_REGISTRY_NAME) is manager.get(
            DG_NODE_REGISTRY_NAME
        )

    def test_duplicate_node_insertion_raises(self):
        # Duplicate protection is inherited from
        # compiler.registry.CanonicalRegistry.insert(), never
        # reimplemented -- inserting the same node id twice must raise.
        from compiler.exceptions import DuplicateIdError

        manager = create_dependency_registry_manager()
        node = DependencyNode(
            node_id="dgnode:compiler_manifest:compiler_manifest",
            node_urn="urn:x",
            node_type="compiler_manifest",
            artifact_key="compiler_manifest",
            graph_id="dg-ns",
            graph_urn="urn:ncert-kg:dg:ns",
        )
        manager.get(DG_NODE_REGISTRY_NAME).insert(node)
        with pytest.raises(DuplicateIdError):
            manager.get(DG_NODE_REGISTRY_NAME).insert(node)


# --------------------------------------------------------------------------
# 4. Dependency Graph generation -- shape and determinism
# --------------------------------------------------------------------------

class TestDependencyGraphGeneration:
    def test_full_pipeline_produces_nonempty_graph(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        graph = result["dependency_graph"]
        assert graph["metadata"]["node_count"] == len(graph["nodes"])
        assert graph["metadata"]["edge_count"] == len(graph["edges"])
        assert graph["metadata"]["node_count"] > 0
        assert graph["metadata"]["edge_count"] > 0

    def test_graph_id_and_urn_match_identity_module(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        metadata = result["dependency_graph"]["metadata"]
        assert metadata["graph_id"] == expected_dg_graph_id(NAMESPACE)
        assert metadata["graph_urn"] == expected_dg_graph_urn(NAMESPACE)
        assert metadata["namespace"] == NAMESPACE
        assert metadata["dependency_graph_schema_version"] == DEPENDENCY_GRAPH_VERSION

    def test_one_compiler_registry_node_per_registry_name(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        node_types = [n["node_type"] for n in result["dependency_graph"]["nodes"]]
        assert node_types.count("compiler_registry") == len(REGISTRY_NAMES)
        artifact_keys = {
            n["artifact_key"]
            for n in result["dependency_graph"]["nodes"]
            if n["node_type"] == "compiler_registry"
        }
        assert artifact_keys == set(REGISTRY_NAMES)

    def test_one_knowledge_graph_registry_node_per_role(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        node_types = [n["node_type"] for n in result["dependency_graph"]["nodes"]]
        assert node_types.count("knowledge_graph_registry") == len(KNOWLEDGE_GRAPH_REGISTRY_ROLES)
        assert set(KNOWLEDGE_GRAPH_REGISTRY_ROLES) == {KG_NODE_REGISTRY_NAME, KG_EDGE_REGISTRY_NAME}

    def test_every_singleton_stage_node_present_for_a_full_chapter(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        node_types = {n["node_type"] for n in result["dependency_graph"]["nodes"]}
        singleton_types = set(DEPENDENCY_NODE_TYPES) - {
            "compiler_registry", "knowledge_graph_registry",
        }
        assert singleton_types <= node_types

    def test_build_metadata_node_depends_on_release_and_both_summaries(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        graph = result["dependency_graph"]
        build_metadata_node_id = expected_dg_node_id("build_metadata", "build_metadata")
        targets = {
            e["target_node_id"] for e in graph["edges"]
            if e["source_node_id"] == build_metadata_node_id
        }
        assert expected_dg_node_id("release_readiness", "release_readiness") in targets
        assert expected_dg_node_id("compiler_build_summary", "compiler_build_summary") in targets
        assert (
            expected_dg_node_id("knowledge_graph_build_summary", "knowledge_graph_build_summary")
            in targets
        )

    def test_every_edge_endpoint_resolves_to_a_real_node(self):
        # No dangling edges: every source_node_id/target_node_id an
        # edge references must exist among this graph's own nodes.
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        graph = result["dependency_graph"]
        node_ids = {n["node_id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            assert edge["source_node_id"] in node_ids
            assert edge["target_node_id"] in node_ids

    def test_missing_artifacts_yield_a_smaller_graph_not_an_error(self):
        result = generate_dependency_graph(**_all_none_kwargs())
        graph = result["dependency_graph"]
        assert graph["metadata"]["node_count"] == 0
        assert graph["metadata"]["edge_count"] == 0
        assert graph["nodes"] == []
        assert graph["edges"] == []

    def test_partial_artifacts_only_create_present_nodes(self):
        kwargs = _all_none_kwargs()
        kwargs["build_metadata"] = {"build_metadata_version": "E1.1"}
        result = generate_dependency_graph(**kwargs)
        graph = result["dependency_graph"]
        assert graph["metadata"]["node_count"] == 1
        assert graph["nodes"][0]["node_type"] == "build_metadata"
        # No release_readiness/compiler_build_summary/knowledge_graph_
        # build_summary nodes exist to depend on, so no edge is created
        # either -- never a dangling edge to a node that was never
        # built.
        assert graph["metadata"]["edge_count"] == 0


# --------------------------------------------------------------------------
# 5. Determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_structurally_identical_graphs(self):
        state = build_full_pipeline_state()
        result_a = run_generate_dependency_graph(state)
        result_b = run_generate_dependency_graph(state)
        graph_a = copy.deepcopy(result_a["dependency_graph"])
        graph_b = copy.deepcopy(result_b["dependency_graph"])
        graph_a["metadata"].pop("generated_at")
        graph_b["metadata"].pop("generated_at")
        assert graph_a == graph_b

    def test_node_and_edge_ids_are_stable_across_runs(self):
        state = build_full_pipeline_state()
        ids_a = sorted(n["node_id"] for n in run_generate_dependency_graph(state)["dependency_graph"]["nodes"])
        ids_b = sorted(n["node_id"] for n in run_generate_dependency_graph(state)["dependency_graph"]["nodes"])
        assert ids_a == ids_b


# --------------------------------------------------------------------------
# 6. Read-only behaviour
# --------------------------------------------------------------------------

class TestReadOnlyBehaviour:
    def test_read_only_over_every_input(self):
        state = build_full_pipeline_state()
        before = copy.deepcopy({
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        })
        run_generate_dependency_graph(state)
        after = {
            k: v for k, v in state.items()
            if k not in ("compiler_registry_manager", "graph_registry_manager")
        }
        assert after == before

    def test_never_mutates_registry_managers(self):
        state = build_full_pipeline_state()
        compiler_names_before = sorted(state["compiler_registry_manager"].names())
        graph_names_before = sorted(state["graph_registry_manager"].names())
        compiler_sizes_before = {
            name: state["compiler_registry_manager"].get(name).size()
            for name in compiler_names_before
        }
        graph_sizes_before = {
            name: state["graph_registry_manager"].get(name).size()
            for name in graph_names_before
        }
        run_generate_dependency_graph(state)
        assert sorted(state["compiler_registry_manager"].names()) == compiler_names_before
        assert sorted(state["graph_registry_manager"].names()) == graph_names_before
        for name in compiler_names_before:
            assert state["compiler_registry_manager"].get(name).size() == compiler_sizes_before[name]
        for name in graph_names_before:
            assert state["graph_registry_manager"].get(name).size() == graph_sizes_before[name]


# --------------------------------------------------------------------------
# 7. State integration -- dependency_graph.state
# --------------------------------------------------------------------------

class TestStateIntegration:
    def test_has_current_is_false_before_set(self):
        assert dependency_graph_state.has_current_dependency_graph() is False
        assert dependency_graph_state.get_current_dependency_graph() is None

    def test_set_then_get_returns_same_object(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        dependency_graph_state.set_current_dependency_graph(result["dependency_graph"])
        assert dependency_graph_state.has_current_dependency_graph() is True
        assert dependency_graph_state.get_current_dependency_graph() is result["dependency_graph"]

    def test_reset_clears_state(self):
        state = build_full_pipeline_state()
        result = run_generate_dependency_graph(state)
        dependency_graph_state.set_current_dependency_graph(result["dependency_graph"])
        dependency_graph_state.reset_dependency_graph_state()
        assert dependency_graph_state.has_current_dependency_graph() is False
        assert dependency_graph_state.get_current_dependency_graph() is None


# --------------------------------------------------------------------------
# 8. Pipeline integration -- pipeline.py wiring
# --------------------------------------------------------------------------

class TestPipelineWiring:
    def test_pipeline_imports_dependency_graph_integration_point(self):
        import pipeline
        assert hasattr(pipeline, "generate_dependency_graph")
        assert hasattr(pipeline, "dependency_graph_state")

    def test_process_chapter_source_calls_e2_after_e1(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e1_index = source.index("finalize_build_metadata(")
        e2_index = source.index("generate_dependency_graph(")
        assert e1_index < e2_index

    def test_e2_call_site_never_touches_chapter_dict(self):
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e2_index = source.index("generate_dependency_graph(")
        chapter_dict_index = source.index("chapter_dict = json_writer.assemble_chapter_json")
        assert e2_index < chapter_dict_index
        assemble_call = source[chapter_dict_index:]
        assert "dependency_graph" not in assemble_call.split(")")[0]

    def test_e2_reuses_the_same_namespace_as_the_knowledge_graph(self):
        # namespace=chapter_reference must be reused, not recomputed --
        # see dependency_graph/build.py's own module docstring.
        import inspect
        import pipeline
        source = inspect.getsource(pipeline.process_chapter)
        e2_call_start = source.index("generate_dependency_graph(")
        e2_call_end = source.index(")", e2_call_start)
        e2_call_text = source[e2_call_start:e2_call_end]
        assert "namespace=chapter_reference" in e2_call_text


# --------------------------------------------------------------------------
# 9. Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_build_metadata_state_untouched_by_e2(self):
        from build_metadata import state as build_metadata_state
        build_metadata_state.reset_build_metadata_state()
        state = build_full_pipeline_state()
        run_generate_dependency_graph(state)
        # generate_dependency_graph() never calls build_metadata_state.
        # set_*, so the module-level state here must remain exactly as
        # build_full_pipeline_state() (which itself never sets it
        # either) left it: unset.
        assert build_metadata_state.has_current_build_metadata() is False

    def test_compiler_manifest_fields_unchanged(self):
        state = build_full_pipeline_state()
        manifest_before = copy.deepcopy(state["compiler_manifest"])
        run_generate_dependency_graph(state)
        assert state["compiler_manifest"] == manifest_before

    def test_build_metadata_dict_unchanged(self):
        state = build_full_pipeline_state()
        build_metadata_before = copy.deepcopy(state["build_metadata"])
        run_generate_dependency_graph(state)
        assert state["build_metadata"] == build_metadata_before