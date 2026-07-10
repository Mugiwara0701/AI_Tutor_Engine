"""
tests/test_registries.py — unit tests for Phase B1's concrete canonical
registries (compiler/registries.py) and their pipeline integration.

Per task instructions, these tests are generated only: they are not
executed here, and no claim is made about whether they currently pass.
"""
from __future__ import annotations

import json

import pytest

from compiler import (
    TopicRegistry,
    ConceptRegistry,
    DefinitionRegistry,
    GlossaryRegistry,
    EquationRegistry,
    FigureRegistry,
    DiagramRegistry,
    TableRegistry,
    ExampleRegistry,
    ActivityRegistry,
    BoxRegistry,
    NoteRegistry,
    WarningRegistry,
    RegistryManager,
    DuplicateIdError,
    ItemNotFoundError,
)
from compiler.registries import (
    REGISTRY_NAMES,
    create_registry_manager,
    populate_registries,
)
from compiler import state as compiler_state
from compiler.state import (
    set_current_registry_manager,
    get_current_registry_manager,
    has_current_registry_manager,
    reset_registry_state,
)


# --------------------------------------------------------------------------
# Helpers -- minimal stand-ins for the dicts modules/canonical.py +
# pipeline.py's _attach_canonical() actually build, keeping only the keys
# these tests care about (id/urn/name/term/title + a couple of payload
# fields), not a full canonical envelope.
# --------------------------------------------------------------------------

def make_concept(id_, name, urn=None, **extra):
    d = {"id": id_, "name": name, "urn": urn or f"urn:concept:{name}"}
    d.update(extra)
    return d


def make_definition(id_, term, page, urn=None, **extra):
    d = {"id": id_, "term": term, "page": page, "urn": urn or f"urn:definition:{term}:{page}"}
    d.update(extra)
    return d


def make_glossary(id_, term, topic, urn=None, **extra):
    d = {"id": id_, "term": term, "topic": topic, "urn": urn or f"urn:glossary:{term}:{topic}"}
    d.update(extra)
    return d


def make_figure(id_, title, page, urn=None, **extra):
    d = {"id": id_, "title": title, "page": page, "urn": urn or f"urn:figure:{page}:{id_}"}
    d.update(extra)
    return d


def make_equation(id_, page, urn=None, **extra):
    d = {"id": id_, "page": page, "latex": extra.pop("latex", ""), "urn": urn or f"urn:equation:{page}:{id_}"}
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# Concrete registry classes: each is just a named CanonicalRegistry
# --------------------------------------------------------------------------
class TestConcreteRegistryClasses:
    @pytest.mark.parametrize(
        "registry_cls,expected_name",
        [
            (ConceptRegistry, "concepts"),
            (DefinitionRegistry, "definitions"),
            (GlossaryRegistry, "glossary"),
            (EquationRegistry, "equations"),
            (FigureRegistry, "figures"),
            (DiagramRegistry, "diagrams"),
            (TableRegistry, "tables"),
            (ExampleRegistry, "examples"),
            (ActivityRegistry, "activities"),
            (BoxRegistry, "boxes"),
            (NoteRegistry, "notes"),
            (WarningRegistry, "warnings"),
        ],
    )
    def test_registry_has_expected_fixed_name(self, registry_cls, expected_name):
        registry = registry_cls()
        assert registry.name == expected_name

    def test_registries_start_empty(self):
        for registry_cls in (ConceptRegistry, DefinitionRegistry, FigureRegistry):
            assert registry_cls().size() == 0

    def test_registries_take_no_required_constructor_args(self):
        # every concrete registry must be constructible with no arguments,
        # since create_registry_manager() instantiates them that way
        for registry_cls in (
            ConceptRegistry, DefinitionRegistry, GlossaryRegistry, EquationRegistry,
            FigureRegistry, DiagramRegistry, TableRegistry, ExampleRegistry,
            ActivityRegistry, BoxRegistry, NoteRegistry, WarningRegistry,
        ):
            registry_cls()  # must not raise


# --------------------------------------------------------------------------
# ConceptRegistry: name-indexed, since pipeline.py already deduplicates
# concepts by case-insensitive name before they reach the registry
# --------------------------------------------------------------------------
class TestConceptRegistry:
    def test_insert_and_get_by_id(self):
        r = ConceptRegistry()
        r.insert(make_concept("c1", "Photosynthesis"))
        assert r.get_by_id("c1")["name"] == "Photosynthesis"

    def test_insert_and_get_by_name_case_insensitive(self):
        r = ConceptRegistry()
        r.insert(make_concept("c1", "Photosynthesis"))
        assert r.get_by_name("photosynthesis")["id"] == "c1"
        assert r.get_by_name("PHOTOSYNTHESIS")["id"] == "c1"

    def test_duplicate_name_different_id_raises(self):
        r = ConceptRegistry()
        r.insert(make_concept("c1", "Photosynthesis"))
        with pytest.raises(Exception):
            r.insert(make_concept("c2", "Photosynthesis"))

    def test_duplicate_id_raises(self):
        r = ConceptRegistry()
        r.insert(make_concept("c1", "Photosynthesis"))
        with pytest.raises(DuplicateIdError):
            r.insert(make_concept("c1", "Different Name"))


# --------------------------------------------------------------------------
# DefinitionRegistry: NOT name-indexed -- the same term legitimately
# recurs across pages within a chapter (see registries.py docstring)
# --------------------------------------------------------------------------
class TestDefinitionRegistry:
    def test_insert_and_get_by_id(self):
        r = DefinitionRegistry()
        r.insert(make_definition("d1", "Osmosis", page=12))
        assert r.get_by_id("d1")["term"] == "Osmosis"

    def test_same_term_different_pages_both_insert_without_conflict(self):
        r = DefinitionRegistry()
        r.insert(make_definition("d1", "Osmosis", page=12))
        r.insert(make_definition("d2", "Osmosis", page=47))
        assert r.size() == 2
        assert r.get_by_id("d1")["page"] == 12
        assert r.get_by_id("d2")["page"] == 47

    def test_get_by_name_is_not_populated(self):
        # DefinitionRegistry does not index by "term"; there is no "name"
        # key on definition dicts, so get_by_name is simply never a hit.
        r = DefinitionRegistry()
        r.insert(make_definition("d1", "Osmosis", page=12))
        assert r.get_by_name("Osmosis") is None

    def test_duplicate_id_still_raises(self):
        r = DefinitionRegistry()
        r.insert(make_definition("d1", "Osmosis", page=12))
        with pytest.raises(DuplicateIdError):
            r.insert(make_definition("d1", "Osmosis", page=12))


# --------------------------------------------------------------------------
# GlossaryRegistry: same non-name-indexed reasoning as DefinitionRegistry
# --------------------------------------------------------------------------
class TestGlossaryRegistry:
    def test_same_term_different_topics_both_insert(self):
        r = GlossaryRegistry()
        r.insert(make_glossary("g1", "Mitosis", topic="t1"))
        r.insert(make_glossary("g2", "Mitosis", topic="t2"))
        assert r.size() == 2


# --------------------------------------------------------------------------
# FigureRegistry / DiagramRegistry / TableRegistry / EquationRegistry:
# duplicate/empty titles must never collide (no name-indexing)
# --------------------------------------------------------------------------
class TestVisualAndEquationRegistries:
    def test_two_figures_with_identical_title_both_insert(self):
        r = FigureRegistry()
        r.insert(make_figure("f1", "Diagram", page=3))
        r.insert(make_figure("f2", "Diagram", page=9))
        assert r.size() == 2

    def test_two_figures_with_empty_title_both_insert(self):
        r = FigureRegistry()
        r.insert(make_figure("f1", "", page=3))
        r.insert(make_figure("f2", "", page=9))
        assert r.size() == 2

    def test_equation_registry_has_no_name_field_but_still_works(self):
        r = EquationRegistry()
        r.insert(make_equation("e1", page=5, latex="E=mc^2"))
        assert r.get_by_id("e1")["latex"] == "E=mc^2"
        assert r.get_by_name("anything") is None

    def test_duplicate_urn_raises_for_figures(self):
        r = FigureRegistry()
        r.insert(make_figure("f1", "A", page=3, urn="urn:figure:3:0"))
        with pytest.raises(Exception):
            r.insert(make_figure("f2", "B", page=3, urn="urn:figure:3:0"))


# --------------------------------------------------------------------------
# create_registry_manager()
# --------------------------------------------------------------------------
class TestCreateRegistryManager:
    def test_creates_all_thirteen_registries(self):
        # 12 original Phase B1 registries + "topics" (Phase C0.1
        # audit-findings refinement -- see compiler/registries.py's own
        # "TOPIC REGISTRY" docstring section).
        manager = create_registry_manager()
        assert set(manager.names()) == set(REGISTRY_NAMES)
        assert len(manager) == 13
        assert isinstance(manager.get("topics"), TopicRegistry)

    def test_every_registry_starts_empty(self):
        manager = create_registry_manager()
        assert manager.total_size() == 0

    def test_registries_are_independent_across_calls(self):
        m1 = create_registry_manager()
        m1.get("concepts").insert(make_concept("c1", "Photosynthesis"))
        m2 = create_registry_manager()
        assert m2.get("concepts").size() == 0

    def test_registry_types_match_concrete_classes(self):
        manager = create_registry_manager()
        assert isinstance(manager.get("concepts"), ConceptRegistry)
        assert isinstance(manager.get("figures"), FigureRegistry)
        assert isinstance(manager.get("equations"), EquationRegistry)


# --------------------------------------------------------------------------
# populate_registries()
# --------------------------------------------------------------------------
class TestPopulateRegistries:
    def test_populates_each_type_into_its_own_registry(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept("c1", "Photosynthesis")],
            definitions=[make_definition("d1", "Osmosis", page=1)],
            glossary=[make_glossary("g1", "Mitosis", topic="t1")],
            figures=[make_figure("f1", "Fig 1", page=1)],
            diagrams=[make_figure("dg1", "Diagram 1", page=2)],
            tables=[make_figure("tb1", "Table 1", page=3)],
            equations=[make_equation("e1", page=4)],
            activities=[{"id": "a1", "activity_type": "group", "page": 5,
                         "urn": "urn:activity:group:5"}],
            boxes=[{"id": "b1", "box_type": "info", "page": 6, "urn": "urn:box:info:6"}],
            warnings=[{"id": "w1", "warning_type": "caution", "page": 7,
                       "urn": "urn:warning:caution:7"}],
            notes=[{"id": "n1", "page": 8, "urn": "urn:note:8"}],
            examples=[{"id": "ex1", "page": 9, "urn": "urn:example:9"}],
        )
        assert manager.get("concepts").size() == 1
        assert manager.get("definitions").size() == 1
        assert manager.get("glossary").size() == 1
        assert manager.get("figures").size() == 1
        assert manager.get("diagrams").size() == 1
        assert manager.get("tables").size() == 1
        assert manager.get("equations").size() == 1
        assert manager.get("activities").size() == 1
        assert manager.get("boxes").size() == 1
        assert manager.get("warnings").size() == 1
        assert manager.get("notes").size() == 1
        assert manager.get("examples").size() == 1
        assert manager.total_size() == 12

    def test_unspecified_lists_leave_registry_empty(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1", "Photosynthesis")])
        assert manager.get("concepts").size() == 1
        assert manager.get("figures").size() == 0
        assert manager.total_size() == 1

    def test_empty_list_leaves_registry_empty(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[])
        assert manager.get("concepts").size() == 0

    def test_returns_the_same_manager_instance(self):
        manager = create_registry_manager()
        returned = populate_registries(manager, concepts=[make_concept("c1", "X")])
        assert returned is manager

    def test_preserves_insertion_order_matching_input_list_order(self):
        manager = create_registry_manager()
        concepts = [make_concept(f"c{i}", f"Concept {i}") for i in range(5)]
        populate_registries(manager, concepts=concepts)
        assert manager.get("concepts").ids() == [f"c{i}" for i in range(5)]

    def test_does_not_mutate_input_objects(self):
        manager = create_registry_manager()
        concept = make_concept("c1", "Photosynthesis")
        original = dict(concept)
        populate_registries(manager, concepts=[concept])
        assert concept == original


# --------------------------------------------------------------------------
# Duplicate protection (reuses B0 infrastructure -- no reimplementation)
# --------------------------------------------------------------------------
class TestDuplicateProtection:
    def test_duplicate_concept_id_across_populate_calls_raises(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1", "Photosynthesis")])
        with pytest.raises(DuplicateIdError):
            populate_registries(manager, concepts=[make_concept("c1", "Photosynthesis")])

    def test_duplicate_definition_id_raises_but_same_term_different_id_does_not(self):
        manager = create_registry_manager()
        populate_registries(manager, definitions=[make_definition("d1", "Osmosis", page=1)])
        # same id -> conflict
        with pytest.raises(DuplicateIdError):
            populate_registries(manager, definitions=[make_definition("d1", "Osmosis", page=1)])
        # same term, different id/page -> allowed (matches pre-B1 behavior)
        populate_registries(manager, definitions=[make_definition("d2", "Osmosis", page=99)])
        assert manager.get("definitions").size() == 2


# --------------------------------------------------------------------------
# Registry lookups
# --------------------------------------------------------------------------
class TestRegistryLookups:
    def test_lookup_by_id_urn_and_name_for_concepts(self):
        manager = create_registry_manager()
        populate_registries(
            manager,
            concepts=[make_concept("c1", "Photosynthesis", urn="urn:concept:photosynthesis")],
        )
        concepts = manager.get("concepts")
        assert concepts.lookup(id="c1")["name"] == "Photosynthesis"
        assert concepts.lookup(urn="urn:concept:photosynthesis")["id"] == "c1"
        assert concepts.lookup(name="photosynthesis")["id"] == "c1"

    def test_lookup_missing_returns_none(self):
        manager = create_registry_manager()
        assert manager.get("concepts").get_by_id("nonexistent") is None

    def test_manager_get_missing_registry_raises(self):
        manager = create_registry_manager()
        with pytest.raises(ItemNotFoundError):
            manager.get("not_a_real_registry")


# --------------------------------------------------------------------------
# Deterministic behaviour
# --------------------------------------------------------------------------
class TestDeterministicBehaviour:
    def test_two_runs_with_same_input_order_produce_identical_serialization(self):
        def build():
            manager = create_registry_manager()
            populate_registries(
                manager,
                concepts=[make_concept("c1", "Alpha"), make_concept("c2", "Beta")],
                figures=[make_figure("f1", "Fig 1", page=1)],
            )
            return manager

        m1, m2 = build(), build()
        assert m1.serialize() == m2.serialize()
        assert m1.to_json() == m2.to_json()

    def test_registry_manager_names_are_in_fixed_order(self):
        m1 = create_registry_manager()
        m2 = create_registry_manager()
        assert m1.names() == m2.names()

    def test_serialize_round_trips_through_json(self):
        manager = create_registry_manager()
        populate_registries(manager, concepts=[make_concept("c1", "Alpha")])
        blob = manager.serialize()
        text = json.dumps(blob)
        restored = json.loads(text)
        assert restored == blob


# --------------------------------------------------------------------------
# RegistryManager lifecycle (compiler/state.py -- B1 refinement pass)
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_registry_state_between_tests():
    """compiler/state.py holds process-wide "current compilation state" --
    reset it before and after every test in this module so no test can
    leak a RegistryManager into another (mirrors why pipeline.py itself
    resets this once per chapter)."""
    reset_registry_state()
    yield
    reset_registry_state()


class TestRegistryManagerLifecycle:
    def test_no_current_manager_before_anything_is_set(self):
        assert get_current_registry_manager() is None
        assert has_current_registry_manager() is False

    def test_set_then_get_returns_the_same_instance(self):
        manager = create_registry_manager()
        set_current_registry_manager(manager)
        assert get_current_registry_manager() is manager
        assert has_current_registry_manager() is True

    def test_set_current_manager_reflects_live_mutations(self):
        # get_current_registry_manager() must return a live reference,
        # not a snapshot/copy -- inserts made after set_current_registry_manager()
        # must still be visible through it.
        manager = create_registry_manager()
        set_current_registry_manager(manager)
        populate_registries(manager, concepts=[make_concept("c1", "Photosynthesis")])
        current = get_current_registry_manager()
        assert current is manager
        assert current.get("concepts").size() == 1

    def test_reset_clears_current_manager(self):
        set_current_registry_manager(create_registry_manager())
        assert has_current_registry_manager() is True
        reset_registry_state()
        assert has_current_registry_manager() is False
        assert get_current_registry_manager() is None

    def test_setting_a_new_manager_replaces_the_previous_one(self):
        first = create_registry_manager()
        second = create_registry_manager()
        set_current_registry_manager(first)
        set_current_registry_manager(second)
        assert get_current_registry_manager() is second
        assert get_current_registry_manager() is not first

    def test_reset_between_chapters_prevents_stale_manager_leakage(self):
        # Simulates pipeline.py's own per-chapter sequence: populate +
        # set for chapter 1, reset (start of chapter 2) before chapter 2
        # has built anything yet -- chapter 2 must never see chapter 1's
        # registries as "current".
        chapter_1_manager = create_registry_manager()
        populate_registries(chapter_1_manager, concepts=[make_concept("c1", "Chapter 1 Concept")])
        set_current_registry_manager(chapter_1_manager)
        assert get_current_registry_manager() is chapter_1_manager

        reset_registry_state()  # start of chapter 2, before it builds anything
        assert get_current_registry_manager() is None

        chapter_2_manager = create_registry_manager()
        populate_registries(chapter_2_manager, concepts=[make_concept("c2", "Chapter 2 Concept")])
        set_current_registry_manager(chapter_2_manager)
        assert get_current_registry_manager() is chapter_2_manager
        assert get_current_registry_manager().get("concepts").get_by_id("c1") is None


# --------------------------------------------------------------------------
# Pipeline integration
# --------------------------------------------------------------------------
class TestPipelineIntegration:
    def test_pipeline_module_exposes_registry_glue(self):
        import pipeline

        assert pipeline.create_registry_manager is create_registry_manager
        assert pipeline.populate_registries is populate_registries

    def test_pipeline_module_wires_registry_lifecycle(self):
        import pipeline

        assert pipeline.compiler_state.set_current_registry_manager is set_current_registry_manager
        assert pipeline.compiler_state.reset_registry_state is reset_registry_state

    def test_process_chapter_resets_and_sets_registry_lifecycle_state(self):
        # Static check (no PDF/VLM run needed): process_chapter must reset
        # prior registry state early (alongside semantic_processor's own
        # reset_chapter_state()) and hand its populated manager to
        # compiler_state.set_current_registry_manager() -- not merely
        # build-and-discard it as a local variable.
        import inspect
        import pipeline

        source = inspect.getsource(pipeline.process_chapter)
        assert "compiler_state.reset_registry_state()" in source
        assert "compiler_state.set_current_registry_manager(registry_manager)" in source
        # the reset must happen before population, and population before
        # the manager is registered as current
        reset_idx = source.index("compiler_state.reset_registry_state()")
        populate_idx = source.index("populate_registries(")
        set_idx = source.index("compiler_state.set_current_registry_manager(")
        assert reset_idx < populate_idx < set_idx

    def test_registry_statistics_logging_is_guarded_by_debug_level_check(self):
        # Task 4 refinement: computing RegistryStatistics (a real
        # sys.getsizeof() scan) must not happen unconditionally every
        # chapter run -- only when DEBUG logging is actually enabled.
        import inspect
        import pipeline

        source = inspect.getsource(pipeline.process_chapter)
        # rindex, not index: the explanatory comment above the guard also
        # mentions "registry_manager.statistics()" in prose (documenting
        # the earlier, ungated version this replaced) -- the actual call
        # is the LAST occurrence in the function body, inside the
        # isEnabledFor(DEBUG) guard.
        stats_call_idx = source.rindex("registry_manager.statistics()")
        guard_idx = source.index("logger.isEnabledFor(logging.DEBUG)")
        assert guard_idx < stats_call_idx

    def test_populate_registries_call_shape_matches_pipeline_object_lists(self):
        # Mirrors the exact call pipeline.py makes right before
        # json_writer.assemble_chapter_json -- one finalized list per
        # canonical object type, all keyword-only.
        manager = create_registry_manager()
        all_concepts = [make_concept("c1", "Concept One")]
        definitions = [make_definition("d1", "Term One", page=1)]
        glossary = [make_glossary("g1", "Glossary One", topic="t1")]
        figures = [make_figure("f1", "Figure One", page=1)]
        diagrams = [make_figure("dg1", "Diagram One", page=2)]
        tables = [make_figure("tb1", "Table One", page=3)]
        equations = [make_equation("e1", page=4)]
        activities = [{"id": "a1", "page": 5, "urn": "urn:activity:5"}]
        boxes = [{"id": "b1", "page": 6, "urn": "urn:box:6"}]
        warnings_list = [{"id": "w1", "page": 7, "urn": "urn:warning:7"}]
        notes = [{"id": "n1", "page": 8, "urn": "urn:note:8"}]
        examples = [{"id": "ex1", "page": 9, "urn": "urn:example:9"}]

        populate_registries(
            manager,
            concepts=all_concepts, definitions=definitions, glossary=glossary,
            figures=figures, diagrams=diagrams, tables=tables, equations=equations,
            activities=activities, boxes=boxes, warnings=warnings_list, notes=notes,
            examples=examples,
        )
        assert manager.total_size() == 12

    def test_process_chapter_builds_a_registry_manager_before_assembling_json(self):
        # Static check that pipeline.py's process_chapter source references
        # the Phase B1 integration point, without requiring a full PDF/VLM
        # run (which is already covered by existing end-to-end tests).
        import inspect
        import pipeline

        source = inspect.getsource(pipeline.process_chapter)
        assert "create_registry_manager" in source
        assert "populate_registries" in source
        # integration must happen before JSON assembly, not after
        assert source.index("populate_registries(") < source.index("assemble_chapter_json(")


# --------------------------------------------------------------------------
# Backward compatibility
# --------------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_registry_population_never_mutates_json_writer_inputs(self):
        # Simulates pipeline.py's finalized lists, confirms populate_registries
        # leaves every object dict byte-for-byte identical (registries store
        # references, not copies, and never write back to the object).
        all_concepts = [make_concept("c1", "Photosynthesis")]
        figures = [make_figure("f1", "Fig 1", page=1)]
        snapshot_concepts = json.dumps(all_concepts, sort_keys=True)
        snapshot_figures = json.dumps(figures, sort_keys=True)

        manager = create_registry_manager()
        populate_registries(manager, concepts=all_concepts, figures=figures)

        assert json.dumps(all_concepts, sort_keys=True) == snapshot_concepts
        assert json.dumps(figures, sort_keys=True) == snapshot_figures

    def test_registry_manager_not_required_for_existing_registry_api(self):
        # Phase B0's generic API keeps working standalone, unaffected by
        # Phase B1's concrete registries being importable from the same
        # package.
        from compiler import CanonicalRegistry

        r = CanonicalRegistry(name="anything")
        r.insert({"id": "x", "name": "Y"})
        assert r.get_by_id("x")["name"] == "Y"

    def test_phase_b0_exceptions_still_importable(self):
        from compiler import DuplicateUrnError, DuplicateNameError, RegistryError

        assert issubclass(DuplicateUrnError, RegistryError)
        assert issubclass(DuplicateNameError, RegistryError)

    def test_registry_lifecycle_addition_does_not_disturb_existing_manager_api(self):
        # The B1-refinement lifecycle layer (compiler/state.py) is
        # additive: RegistryManager itself gained no new required
        # constructor args or changed methods.
        manager = create_registry_manager()
        assert manager.total_size() == 0
        assert isinstance(manager, RegistryManager)