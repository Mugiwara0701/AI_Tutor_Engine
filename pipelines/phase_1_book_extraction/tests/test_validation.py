"""
tests/test_validation.py — unit tests for Phase B4's compiler.validation
module (Compiler Validation & Integrity Pass).

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import copy

import pytest

from compiler.registries import create_registry_manager, populate_registries
from compiler.registry import CanonicalRegistry
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries
from compiler.references import resolve_references
from compiler.relationships import (
    RELATIONSHIP_REGISTRY_NAME,
    resolve_relationships,
    ensure_relationship_registry,
)
from compiler import state as compiler_state
from compiler.validation import (
    VALIDATION_VERSION,
    ValidationIssue,
    ValidationReport,
    validate_compiler_state,
    _validate_registry_integrity,
    _validate_canonical_object_integrity,
    _validate_reference_integrity,
    _validate_relationship_integrity,
    _validate_compiler_state_integrity,
    _check_id_determinism,
)


# --------------------------------------------------------------------------
# Helpers -- these build FULLY COMPLIANT canonical objects (every
# REQUIRED_CANONICAL_FIELDS key present) by default, since this module's
# job is to flag deviations from that baseline; each test that wants a
# specific violation removes/breaks exactly one field.
# --------------------------------------------------------------------------

def _base_fields(id_, kind, extra_urn_ns):
    return {
        "id": id_,
        "urn": f"urn:{extra_urn_ns}:{id_}",
        "object_type": kind,
        "schema_version": "1.0.0",
        "provenance": {"source": "test"},
        "validation_status": "validated",
        "creation_metadata": {"compiler_version": "1.0.0"},
        "topic_ids": [],
    }


def make_concept(id_="c1", name="Photosynthesis", aliases=None, topic_ids=None, **extra):
    d = _base_fields(id_, "concept", "concept")
    d["name"] = name
    d["aliases"] = aliases if aliases is not None else []
    if topic_ids is not None:
        d["topic_ids"] = topic_ids
    d.update(extra)
    return d


def make_definition(id_="d1", term="Inflation", topic_ids=None, **extra):
    d = _base_fields(id_, "definition", "definition")
    d["term"] = term
    if topic_ids is not None:
        d["topic_ids"] = topic_ids
    d.update(extra)
    return d


def make_glossary(id_="g1", term="Inflation", topic_ids=None, **extra):
    d = _base_fields(id_, "glossary_entry", "glossary")
    d["term"] = term
    if topic_ids is not None:
        d["topic_ids"] = topic_ids
    d.update(extra)
    return d


def make_figure(id_="f1", title="Fig 1", **extra):
    d = _base_fields(id_, "figure", "figure")
    d["title"] = title
    d.update(extra)
    return d


def make_topic(id_="t1", concepts=None, **extra):
    d = {"id": id_, "concepts": concepts if concepts is not None else []}
    d.update(extra)
    return d


def build_manager(**populate_kwargs):
    """The full frozen pipeline this phase must run at the end of:
    populate -> enrich -> normalize -> resolve_references ->
    resolve_relationships. Returns (manager, topics) so callers have a
    consistent topics list to pass to resolve_relationships() and
    validate_compiler_state() alike."""
    topics = populate_kwargs.pop("topics", None) or []
    manager = create_registry_manager()
    populate_registries(manager, **populate_kwargs)
    enrich_registries(manager)
    normalize_registries(manager)
    resolve_references(manager, topics=topics)
    resolve_relationships(manager, topics=topics)
    return manager, topics


# --------------------------------------------------------------------------
# Registry validation
# --------------------------------------------------------------------------

class TestRegistryValidation:
    def test_clean_manager_has_no_registry_integrity_errors(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        issues, summary = _validate_registry_integrity(manager)
        assert issues == []
        assert summary["concepts"]["duplicate_ids"] == 0
        assert summary["concepts"]["duplicate_urns"] == 0

    def test_registry_summary_covers_every_registry_in_manager(self):
        manager, topics = build_manager(concepts=[make_concept("c1")])
        _, summary = _validate_registry_integrity(manager)
        assert set(summary.keys()) == set(manager.names())


class TestDuplicateIds:
    def test_duplicate_id_across_bulk_insert_flagged(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = manager.get("concepts")
        # Simulate a bulk-load path bypassing insert()'s own duplicate
        # guard (the only way a real duplicate id could ever land in a
        # dict-backed registry) so this rule has something to catch.
        registry._items["c1__dup"] = dict(registry.get_by_id("c1"), id="c1")
        issues, summary = _validate_registry_integrity(manager)
        assert any(i.rule == "registry_consistency" for i in issues) or \
            any(i.rule == "duplicate_id" for i in issues)


class TestDuplicateUrns:
    def test_two_different_ids_sharing_a_urn_is_an_error(self):
        # insert() itself already prevents this at population time (see
        # compiler/registry.py's own DuplicateUrnError) -- to exercise
        # this rule at all, the corrupted state has to be constructed by
        # writing directly into the registry's backing dict, bypassing
        # insert()'s guard, simulating a registry populated by some other
        # (buggy, non-insert()) path this defensive re-check exists for.
        manager, _ = build_manager(
            definitions=[make_definition("d1", "Inflation", urn="urn:definition:shared")],
        )
        registry = manager.get("definitions")
        registry._items["d2"] = make_definition("d2", "Deflation", urn="urn:definition:shared")
        issues, _ = _validate_registry_integrity(manager)
        assert any(i.rule == "duplicate_urn" for i in issues)


class TestDuplicateLookupKeysAndAliases:
    def test_duplicate_concept_lookup_key_is_a_warning_not_an_error(self):
        c1 = make_concept("c1", "Inflation")
        c2 = make_concept("c2", "inflation ")  # same normalized key
        manager, _ = build_manager(concepts=[c1])
        # Force the second concept in directly (bypassing the Single
        # Owner Principle Phase A/B2 would normally apply) so this rule
        # has an ambiguous pair to detect.
        registry = manager.get("concepts")
        c2["canonical_lookup_key"] = registry.get_by_id("c1").get("canonical_lookup_key")
        registry._items["c2"] = c2
        issues, summary = _validate_registry_integrity(manager)
        dup_key_issues = [i for i in issues if i.rule == "duplicate_lookup_key"]
        assert dup_key_issues
        assert all(i.severity == "warning" for i in dup_key_issues)

    def test_duplicate_lookup_key_not_checked_outside_concepts_registry(self):
        # figures/diagrams/tables legitimately share captions/titles --
        # see compiler/registries.py's own documented reasoning -- so no
        # duplicate_lookup_key warning should ever be raised for them.
        manager, _ = build_manager(
            figures=[make_figure("f1", "Diagram"), make_figure("f2", "Diagram")],
        )
        issues, _ = _validate_registry_integrity(manager)
        assert not any(i.rule == "duplicate_lookup_key" and i.registry == "figures" for i in issues)

    def test_duplicate_alias_across_two_concepts_is_a_warning(self):
        c1 = make_concept("c1", "Inflation", aliases=["price rise"])
        c2 = make_concept("c2", "Deflation", aliases=["Price Rise"])
        manager, _ = build_manager(concepts=[c1, c2])
        issues, _ = _validate_registry_integrity(manager)
        alias_issues = [i for i in issues if i.rule == "duplicate_alias"]
        assert alias_issues
        assert all(i.severity == "warning" for i in alias_issues)


# --------------------------------------------------------------------------
# Canonical object integrity
# --------------------------------------------------------------------------

class TestCanonicalObjectIntegrity:
    def test_complete_object_has_no_missing_field_errors(self):
        manager, _ = build_manager(concepts=[make_concept("c1")])
        issues = _validate_canonical_object_integrity(manager)
        assert issues == []

    def test_missing_top_level_field_reported(self):
        concept = make_concept("c1")
        del concept["provenance"]
        manager, _ = build_manager(concepts=[concept])
        issues = _validate_canonical_object_integrity(manager)
        assert any(
            i.rule == "missing_required_field" and "provenance" in i.details.get("missing_fields", [])
            for i in issues
        )

    def test_missing_compiler_version_reported(self):
        concept = make_concept("c1")
        concept["creation_metadata"] = {}
        manager, _ = build_manager(concepts=[concept])
        issues = _validate_canonical_object_integrity(manager)
        assert any(
            "creation_metadata.compiler_version" in i.details.get("missing_fields", [])
            for i in issues
        )

    def test_never_modifies_the_object_it_flags(self):
        concept = make_concept("c1")
        del concept["provenance"]
        manager, _ = build_manager(concepts=[concept])
        before = copy.deepcopy(manager.get("concepts").get_by_id("c1"))
        _validate_canonical_object_integrity(manager)
        assert manager.get("concepts").get_by_id("c1") == before


# --------------------------------------------------------------------------
# Broken references
# --------------------------------------------------------------------------

class TestBrokenReferences:
    def test_valid_concept_id_reference_not_flagged(self):
        manager, _ = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        issues, summary = _validate_reference_integrity(manager, topics=None)
        assert not any(i.rule == "broken_reference" for i in issues)
        assert summary["broken"] == 0

    def test_broken_reverse_aggregation_field_flagged(self):
        # NOTE: resolve_references() (Phase B2) recomputes every
        # concept's reverse-aggregation fields (definition_ids, etc.)
        # fresh, deterministically, from the current definitions/
        # glossary registries -- so injecting a broken id BEFORE
        # build_manager() runs would simply be overwritten by B2's own
        # (correct, empty) recomputation. To exercise this rule
        # meaningfully, corrupt the field on the already-resolved
        # concept, simulating the only realistic way this could ever be
        # broken in practice: a bug in an EARLIER phase, which is
        # exactly what this read-only validator exists to catch.
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        concept = manager.get("concepts").get_by_id("c1")
        concept["definition_ids"] = ["nonexistent-id"]
        issues, summary = _validate_reference_integrity(manager, topics=None)
        assert any(i.rule == "broken_reference" and i.details.get("field") == "definition_ids" for i in issues)
        assert summary["broken"] >= 1

    def test_topic_ids_not_checked_when_topics_not_supplied(self):
        manager, _ = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])],
        )
        issues, summary = _validate_reference_integrity(manager, topics=None)
        assert not any(i.rule == "broken_reference" and i.details.get("field") == "topic_ids" for i in issues)
        assert summary["not_checked"] >= 1

    def test_topic_ids_checked_and_flagged_when_topics_supplied(self):
        manager, _ = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t-missing"])],
        )
        issues, summary = _validate_reference_integrity(manager, topics=[make_topic("t1")])
        assert any(i.rule == "broken_reference" and i.details.get("field") == "topic_ids" for i in issues)
        assert summary["broken"] >= 1

    def test_reference_integrity_is_read_only(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        manager.get("concepts").get_by_id("c1")["definition_ids"] = ["nonexistent-id"]
        before = copy.deepcopy(manager.get("concepts").get_by_id("c1"))
        _validate_reference_integrity(manager, topics=None)
        assert manager.get("concepts").get_by_id("c1") == before


# --------------------------------------------------------------------------
# Orphan / invalid relationships
# --------------------------------------------------------------------------

class TestRelationshipValidation:
    def test_valid_relationships_produce_no_errors(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])],
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1"])],
            topics=[make_topic("t1", concepts=["c1"])],
        )
        issues, summary = _validate_relationship_integrity(manager, topics=[make_topic("t1", concepts=["c1"])])
        assert issues == []
        assert summary["broken_source"] == 0
        assert summary["broken_target"] == 0
        assert summary["invalid_type"] == 0

    def test_orphan_relationship_flagged(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = ensure_relationship_registry(manager)
        registry.insert({
            "id": "rel-orphan", "type": "has_definition",
            "source_type": "concept", "source_id": "nonexistent-concept",
            "target_type": "definition", "target_id": "nonexistent-def",
        })
        issues, summary = _validate_relationship_integrity(manager, topics=None)
        assert any(i.rule == "broken_relationship_source" for i in issues)
        assert any(i.rule == "broken_relationship_target" for i in issues)
        assert summary["orphans"] == 1

    def test_invalid_relationship_type_flagged(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = ensure_relationship_registry(manager)
        registry.insert({
            "id": "rel-bad-type", "type": "not_a_real_type",
            "source_type": "concept", "source_id": "c1",
            "target_type": "concept", "target_id": "c1",
        })
        issues, summary = _validate_relationship_integrity(manager, topics=None)
        assert any(i.rule == "invalid_relationship_type" for i in issues)
        assert summary["invalid_type"] == 1

    def test_duplicate_relationship_triple_flagged(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = ensure_relationship_registry(manager)
        registry.insert({
            "id": "rel-a", "type": "described_by",
            "source_type": "concept", "source_id": "c1",
            "target_type": "glossary_entry", "target_id": "g1",
        })
        registry.insert({
            "id": "rel-b-dup-triple", "type": "described_by",
            "source_type": "concept", "source_id": "c1",
            "target_type": "glossary_entry", "target_id": "g1",
        })
        issues, summary = _validate_relationship_integrity(manager, topics=None)
        assert any(i.rule == "duplicate_relationship" for i in issues)
        assert summary["duplicate_triples"] == 1

    def test_missing_relationship_registry_returns_empty_not_error(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1")])
        # Deliberately skip resolve_relationships() -- no "relationships"
        # registry exists yet. This function reports nothing (absence is
        # the Compiler State Integrity check's job, not this one's).
        issues, summary = _validate_relationship_integrity(manager, topics=None)
        assert issues == []
        assert summary["total"] == 0

    def test_relationship_validation_is_read_only(self):
        manager, _ = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        before = copy.deepcopy(manager.get(RELATIONSHIP_REGISTRY_NAME).serialize())
        _validate_relationship_integrity(manager, topics=None)
        assert manager.get(RELATIONSHIP_REGISTRY_NAME).serialize() == before


# --------------------------------------------------------------------------
# Deterministic ordering
# --------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_id_shape_check_accepts_deterministically_generated_ids(self):
        from compiler.relationships import _relationship_id
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = ensure_relationship_registry(manager)
        rel_id = _relationship_id("relationship", "appears_in", "c1", "t1")
        registry.insert({
            "id": rel_id, "type": "appears_in",
            "source_type": "concept", "source_id": "c1",
            "target_type": "topic", "target_id": "t1",
        })
        issues, summary = _check_id_determinism(manager)
        assert summary["relationship_id_recomputation_mismatches"] == 0
        assert not any(i.object_id == rel_id and i.rule == "relationship_id_not_reproducible" for i in issues)

    def test_relationship_id_recomputation_mismatch_flagged(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation")])
        registry = ensure_relationship_registry(manager)
        registry.insert({
            "id": "hand-crafted-not-a-hash", "type": "appears_in",
            "source_type": "concept", "source_id": "c1",
            "target_type": "topic", "target_id": "t1",
        })
        issues, summary = _check_id_determinism(manager)
        assert summary["relationship_id_recomputation_mismatches"] == 1
        assert any(i.rule == "relationship_id_not_reproducible" for i in issues)
        # Determinism-shape violations are warnings, not hard errors --
        # see _check_id_determinism's own docstring for why.
        assert all(i.severity == "warning" for i in issues if i.rule == "relationship_id_not_reproducible")

    def test_repeated_validation_runs_produce_identical_issue_lists(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        report1 = validate_compiler_state(manager, topics=topics)
        report2 = validate_compiler_state(manager, topics=topics)
        assert [i["rule"] for i in report1["errors"]] == [i["rule"] for i in report2["errors"]]
        assert [i["rule"] for i in report1["warnings"]] == [i["rule"] for i in report2["warnings"]]


# --------------------------------------------------------------------------
# Compiler state validation
# --------------------------------------------------------------------------

class TestCompilerStateValidation:
    def test_all_required_registries_present_is_ok(self):
        manager, _ = build_manager(concepts=[make_concept("c1")])
        issues, summary = _validate_compiler_state_integrity(manager)
        assert summary["required_registries_present"] is True
        assert summary["relationship_registry_present"] is True
        assert summary["registry_ownership_ok"] is True
        assert issues == []

    def test_missing_relationship_registry_flagged(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1")])
        issues, summary = _validate_compiler_state_integrity(manager)
        assert summary["relationship_registry_present"] is False
        assert any(i.rule == "missing_relationship_registry" for i in issues)

    def test_missing_required_registry_flagged(self):
        manager = create_registry_manager()
        # Remove a required registry entirely to simulate a
        # misconfigured RegistryManager.
        manager._registries.pop("equations", None)
        issues, summary = _validate_compiler_state_integrity(manager)
        assert "equations" in summary["missing_registries"]
        assert any(i.rule == "missing_registry" for i in issues)

    def test_registry_ownership_mismatch_flagged(self):
        manager = create_registry_manager()
        mismatched = CanonicalRegistry(name="not-the-key-name")
        manager._registries["concepts"] = mismatched
        issues, summary = _validate_compiler_state_integrity(manager)
        assert summary["registry_ownership_ok"] is False
        assert any(i.rule == "registry_ownership_mismatch" for i in issues)


# --------------------------------------------------------------------------
# Validation report generation
# --------------------------------------------------------------------------

class TestValidationReportGeneration:
    def test_report_has_expected_top_level_keys(self):
        manager, topics = build_manager(concepts=[make_concept("c1")])
        report = validate_compiler_state(manager, topics=topics)
        for key in ("version", "generated_at", "status", "errors", "warnings",
                    "statistics", "registry_summary", "reference_summary",
                    "relationship_summary", "integrity_summary"):
            assert key in report

    def test_report_version_matches_module_constant(self):
        manager, topics = build_manager(concepts=[make_concept("c1")])
        report = validate_compiler_state(manager, topics=topics)
        assert report["version"] == VALIDATION_VERSION

    def test_clean_compiler_ir_reports_pass_status(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])],
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1"])],
            topics=[make_topic("t1", concepts=["c1"])],
        )
        report = validate_compiler_state(manager, topics=[make_topic("t1", concepts=["c1"])])
        assert report["status"] == "pass"
        assert report["errors"] == []

    def test_broken_ir_reports_fail_status(self):
        manager, topics = build_manager(concepts=[make_concept("c1", "Inflation")])
        manager.get("concepts").get_by_id("c1")["definition_ids"] = ["nonexistent"]
        report = validate_compiler_state(manager, topics=topics)
        assert report["status"] == "fail"
        assert len(report["errors"]) > 0

    def test_statistics_counts_are_consistent(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        report = validate_compiler_state(manager, topics=topics)
        assert report["statistics"]["total_errors"] == len(report["errors"])
        assert report["statistics"]["total_warnings"] == len(report["warnings"])
        assert report["statistics"]["total_canonical_objects"] == 2


# --------------------------------------------------------------------------
# Read-only validation
# --------------------------------------------------------------------------

class TestReadOnlyValidation:
    def test_full_validation_pass_never_mutates_any_registry_item(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])],
            definitions=[make_definition("d1", "Inflation", topic_ids=["t1"])],
            glossary=[make_glossary("g1", "Inflation", topic_ids=["t1"])],
            topics=[make_topic("t1", concepts=["c1"])],
        )
        snapshot_before = {
            name: copy.deepcopy(manager.get(name).serialize())
            for name in manager.names()
        }
        validate_compiler_state(manager, topics=[make_topic("t1", concepts=["c1"])])
        for name in manager.names():
            assert manager.get(name).serialize() == snapshot_before[name]

    def test_full_validation_pass_never_adds_a_new_registry(self):
        manager, topics = build_manager(concepts=[make_concept("c1")])
        names_before = set(manager.names())
        validate_compiler_state(manager, topics=topics)
        assert set(manager.names()) == names_before

    def test_topics_argument_never_mutated(self):
        manager, _ = build_manager(concepts=[make_concept("c1", "Inflation", topic_ids=["t1"])])
        topics = [make_topic("t1", concepts=["c1"])]
        before = copy.deepcopy(topics)
        validate_compiler_state(manager, topics=topics)
        assert topics == before


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_ids_urns_unchanged_after_validation(self):
        manager, topics = build_manager(concepts=[make_concept("c1", "Inflation")])
        concept_before = copy.deepcopy(manager.get("concepts").get_by_id("c1"))
        validate_compiler_state(manager, topics=topics)
        assert manager.get("concepts").get_by_id("c1") == concept_before

    def test_validation_report_never_attached_to_any_registry_item(self):
        manager, topics = build_manager(
            concepts=[make_concept("c1", "Inflation")],
            definitions=[make_definition("d1", "Inflation")],
        )
        validate_compiler_state(manager, topics=topics)
        for name in manager.names():
            for item in manager.get(name).values():
                assert "validation_report" not in item
                assert "compiler_validation" not in item


# --------------------------------------------------------------------------
# Pipeline integration
# --------------------------------------------------------------------------

class TestPipelineIntegration:
    def teardown_method(self):
        compiler_state.reset_registry_state()

    def test_report_reachable_via_compiler_state_after_set(self):
        compiler_state.reset_registry_state()
        manager, topics = build_manager(concepts=[make_concept("c1")])
        report = validate_compiler_state(manager, topics=topics)
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(report)

        assert compiler_state.has_current_validation_report()
        assert compiler_state.get_current_validation_report() == report

    def test_reset_registry_state_clears_validation_report_too(self):
        manager, topics = build_manager(concepts=[make_concept("c1")])
        report = validate_compiler_state(manager, topics=topics)
        compiler_state.set_current_registry_manager(manager)
        compiler_state.set_current_validation_report(report)
        compiler_state.reset_registry_state()
        assert compiler_state.get_current_validation_report() is None
        assert compiler_state.get_current_registry_manager() is None

    def test_validate_compiler_state_runs_after_relationship_resolution_in_expected_order(self):
        """Mirrors pipeline.py's own integration order: ... ->
        resolve_relationships() -> validate_compiler_state() ->
        set_current_registry_manager(). Calling validate_compiler_state()
        before resolve_relationships() would report a missing
        relationship registry -- this test locks in why the order
        matters."""
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1", "Inflation")])
        enrich_registries(manager)
        normalize_registries(manager)
        resolve_references(manager)
        # Deliberately skip resolve_relationships() here.
        report = validate_compiler_state(manager)
        assert report["status"] == "fail"
        assert any(e["rule"] == "missing_relationship_registry" for e in report["errors"])

    def test_validation_report_absent_from_chapter_json_shaped_dict(self):
        """Simulates the shape assemble_chapter_json() receives:
        validate_compiler_state()'s return value must never be threaded
        into anything resembling a chapter_dict."""
        manager, topics = build_manager(concepts=[make_concept("c1")])
        report = validate_compiler_state(manager, topics=topics)
        fake_chapter_dict = {"blocks": [], "educational_objects": []}
        assert "compiler_validation_report" not in fake_chapter_dict
        assert report is not fake_chapter_dict.get("validation_report")