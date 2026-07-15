"""
tests/test_phase_a_finalization.py — dedicated tests for the Phase A
finalization fixes (see MIGRATIONS.md and config.SCHEMA_VERSION's policy
comment for the full write-up):

  Fix 1 (A3, identity consistency) — canonical_namespace/chapter_reference
    must be computed AFTER script-mismatch recovery, so every id/urn for a
    chapter is derived from the same final chapter title.
  Fix 2 (schema version) — TopicNode.concepts' meaning change (names -> ids)
    is a MAJOR schema_version bump (1.0.0 -> 2.0.0), documented in
    MIGRATIONS.md.
  Fix 3 (Figure/Table/Diagram.concept_ids) — no dedicated test: this fix is
    "leave existing behaviour unchanged, add a code comment", not a
    behavior change, so there's nothing new to assert (still an empty
    list, matching Fix 3's design comment in pipeline.py right above the
    figures/diagrams/tables loops).
  Fix 4 — this file.

Covers: canonical_fields(), resolve_concept_ids(), make_id(), make_urn(),
concept registry deduplication, schema version migration.

Run: python -m pytest tests/test_phase_a_finalization.py -v
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import pipeline
from modules import canonical
from modules.pdf_parser import make_id, make_urn, slugify
from schemas.chapter_schema import CanonicalObjectBase, ChapterJSON
from schemas.educational_objects_schema import EducationalObjectsDocument


# ---------------------------------------------------------------------------
# canonical.canonical_fields()
# ---------------------------------------------------------------------------

def test_canonical_fields_builds_urn_from_namespace_and_parts():
    fields = canonical.canonical_fields(
        object_id="some-id-abc123", object_type="concept", namespace="my-book:my-chapter",
        urn_parts=["concept", "Photosynthesis"],
    )
    assert fields["urn"] == make_urn("my-book:my-chapter", "concept", "Photosynthesis")
    assert fields["id"] == "some-id-abc123"
    assert fields["object_type"] == "concept"


def test_canonical_fields_never_mints_its_own_id():
    """canonical_fields() must always echo back the id it was given, never
    derive a different one -- id minting is exclusively make_id()'s job
    (see canonical.py's module docstring, point 1)."""
    fields = canonical.canonical_fields(
        object_id="caller-supplied-id", object_type="definition", namespace="ns",
        urn_parts=["definition", "term"],
    )
    assert fields["id"] == "caller-supplied-id"


def test_canonical_fields_uses_current_schema_version():
    fields = canonical.canonical_fields(
        object_id="x", object_type="concept", namespace="ns", urn_parts=["concept", "x"],
    )
    assert fields["schema_version"] == config.SCHEMA_VERSION
    assert fields["creation_metadata"]["compiler_version"] == config.SCHEMA_VERSION


def test_canonical_fields_defaults_optional_lists_to_empty():
    fields = canonical.canonical_fields(
        object_id="x", object_type="figure", namespace="ns", urn_parts=["figure", "0", "0"],
    )
    assert fields["topic_ids"] == []
    assert fields["concept_ids"] == []
    assert fields["duplicate_lineage"] == []
    assert fields["validation_status"] == "unvalidated"


def test_canonical_fields_passes_through_optional_values():
    fields = canonical.canonical_fields(
        object_id="x", object_type="concept", namespace="ns", urn_parts=["concept", "x"],
        subject="economics", chapter_reference="book:chapter",
        topic_ids=["t1", "t2"], concept_ids=["c1"], source_page=3, confidence=0.75,
    )
    assert fields["subject"] == "economics"
    assert fields["chapter_reference"] == "book:chapter"
    assert fields["topic_ids"] == ["t1", "t2"]
    assert fields["concept_ids"] == ["c1"]
    assert fields["provenance"]["source_page"] == 3
    assert fields["extraction_confidence"] == 0.75


# ---------------------------------------------------------------------------
# canonical.resolve_concept_ids()
# ---------------------------------------------------------------------------

def test_resolve_concept_ids_looks_up_case_insensitively():
    registry = {"photosynthesis": "concept-abc123"}
    assert canonical.resolve_concept_ids(["Photosynthesis"], registry) == ["concept-abc123"]


def test_resolve_concept_ids_preserves_first_seen_order_and_dedups():
    registry = {"a": "id-a", "b": "id-b"}
    result = canonical.resolve_concept_ids(["A", "B", "a", "B"], registry)
    assert result == ["id-a", "id-b"]


def test_resolve_concept_ids_silently_skips_unregistered_names():
    """Concept linkage is best-effort enrichment, not a hard validation
    gate -- a name absent from the registry must be dropped, not raise."""
    registry = {"known": "id-known"}
    result = canonical.resolve_concept_ids(["known", "unknown concept"], registry)
    assert result == ["id-known"]


def test_resolve_concept_ids_handles_empty_input():
    assert canonical.resolve_concept_ids([], {"a": "id-a"}) == []
    assert canonical.resolve_concept_ids(None, {"a": "id-a"}) == []


def test_resolve_concept_ids_skips_blank_names():
    registry = {"a": "id-a"}
    assert canonical.resolve_concept_ids(["   ", "a"], registry) == ["id-a"]


# ---------------------------------------------------------------------------
# make_id() — deterministic id generation
# ---------------------------------------------------------------------------

def test_make_id_is_deterministic_across_calls():
    a = make_id("National Income Accounting", "definition", "GDP", "3")
    b = make_id("National Income Accounting", "definition", "GDP", "3")
    assert a == b


def test_make_id_changes_when_any_part_changes():
    base = make_id("National Income Accounting", "definition", "GDP", "3")
    diff_title = make_id("Macroeconomics", "definition", "GDP", "3")
    diff_term = make_id("National Income Accounting", "definition", "GNP", "3")
    assert base != diff_title
    assert base != diff_term


def test_make_id_reflects_recovered_title_not_original(monkeypatch):
    """A3: if script-mismatch recovery corrects the chapter title, make_id()
    (called with the corrected title, per Fix 1) must produce a different,
    new-title-derived id -- not silently keep reusing the pre-recovery id."""
    garbled_id = make_id("jkVªh; vk; dk ys[kkadu", "concept", "GDP")
    recovered_id = make_id("राष्ट्रीय आय का लेखांकन", "concept", "GDP")
    assert garbled_id != recovered_id


def test_make_id_contains_no_randomness():
    """No UUID/timestamp component: id is a pure function of its parts."""
    ids = {make_id("same", "parts", "here") for _ in range(5)}
    assert len(ids) == 1


def test_make_id_format_is_slug_dash_hash():
    result = make_id("Some Chapter", "concept", "Photosynthesis")
    slug_part, _, hash_part = result.rpartition("-")
    expected_slug = slugify("Some Chapter", "concept", "Photosynthesis")[:60]
    assert slug_part == expected_slug
    assert len(hash_part) == 6
    assert all(c in "0123456789abcdef" for c in hash_part)


# ---------------------------------------------------------------------------
# make_urn() — deterministic urn generation
# ---------------------------------------------------------------------------

def test_make_urn_is_deterministic_across_calls():
    a = make_urn("book:chapter", "concept", "GDP")
    b = make_urn("book:chapter", "concept", "GDP")
    assert a == b


def test_make_urn_has_expected_hierarchical_format():
    urn = make_urn("business-part-1:nature-of-management", "concept", "Planning")
    assert urn.startswith("urn:ncert-kg:")
    assert "business-part-1:nature-of-management" in urn


def test_make_urn_changes_when_namespace_changes():
    """This is exactly what Fix 1 protects: if canonical_namespace is
    derived from a different chapter title, the urn changes too, so
    urn/chapter_reference/id all stay in lockstep."""
    urn_before = make_urn("book:jkvªh-vk-dk-ys-kkadu", "concept", "GDP")
    urn_after = make_urn("book:rashtriya-aay-ka-lekhankan", "concept", "GDP")
    assert urn_before != urn_after


# ---------------------------------------------------------------------------
# Fix 1 — identity consistency: canonical_namespace/chapter_reference must
# be computed after script-mismatch recovery, not before
# ---------------------------------------------------------------------------

def test_canonical_namespace_is_computed_after_recovery_not_before():
    """Regression guard for A3: `canonical_namespace =` must appear in
    pipeline.process_chapter's source AFTER the call to
    _recover_script_mismatched_text(, not before it. Before this fix, the
    namespace/chapter_reference were frozen off the pre-recovery title
    while every make_id()/make_urn() call later in the function read the
    live (post-recovery) structure.chapter_title -- producing an id/urn
    whose own namespace/chapter_reference didn't match the title it was
    keyed from whenever recovery actually changed the title."""
    source = inspect.getsource(pipeline.process_chapter)
    recovery_call_pos = source.index("_recover_script_mismatched_text(")
    namespace_assignment_pos = source.index("canonical_namespace = f")
    assert namespace_assignment_pos > recovery_call_pos, (
        "canonical_namespace must be computed after script-mismatch recovery runs, "
        "not before -- otherwise ids/urns (which read the live, post-recovery "
        "chapter title) can disagree with canonical_namespace/chapter_reference "
        "(which would be frozen off the pre-recovery title)"
    )


def test_chapter_slug_is_computed_after_recovery_not_before():
    source = inspect.getsource(pipeline.process_chapter)
    recovery_call_pos = source.index("_recover_script_mismatched_text(")
    slug_assignment_pos = source.index("chapter_slug = slugify(structure.chapter_title)")
    assert slug_assignment_pos > recovery_call_pos


# ---------------------------------------------------------------------------
# Concept registry deduplication
# ---------------------------------------------------------------------------

def test_concept_registry_keys_on_slugify_in_pipeline_source():
    """Regression guard for the "Single Owner Principle" fix described in
    pipeline.py, and for the DUPLICATE-ID INVESTIGATION FIX in the same
    comment block: the concept registry must be keyed by slugify(name) --
    the SAME normalization make_id()/make_urn() themselves use for this
    object -- not by a weaker, independently-chosen one like
    name.lower(). name.lower() alone only folds case; it does not fold
    punctuation/whitespace the way slugify() (and therefore the canonical
    id itself) does, so two name spellings that differ only in
    punctuation/whitespace (e.g. "Science vs Art" vs "Science vs. Art")
    used to get DIFFERENT name.lower() dedup keys -- so this dict happily
    created two separate concept_registry records -- while colliding on
    the IDENTICAL make_id()/make_urn() id/urn, which populate_registries()
    -> CanonicalRegistry.insert() then rejects with DuplicateIdError. Using
    slugify() for the dedup key closes that gap: any two spellings that
    would collide on id also collide on this key, and are correctly
    merged into one record before registry insertion ever runs."""
    source = inspect.getsource(pipeline.process_chapter)
    assert "key = slugify(name)" in source
    assert 'existing = concept_registry.get(key)' in source
    # the merge branch: a second mention of an already-registered concept
    # must extend `topics`, not create a second record.
    assert 'existing["topics"].append(t.id)' in source


def test_make_id_and_make_urn_collapse_case_and_punctuation_via_slugify():
    """The property the dedup key relies on: slugify() (used inside both
    make_id and make_urn) lowercases its input AND collapses every
    non-letter/mark/number character (spaces, periods, ...) to a single
    '-'. So "Photosynthesis"/"photosynthesis" (case only) AND "Science vs
    Art"/"Science vs. Art" (case + punctuation) each produce the SAME
    id/urn once resolved -- both pairs must therefore be treated as the
    same concept by the dedup key, not just the case-only pair."""
    id_a = make_id("Some Chapter", "concept", "Photosynthesis")
    id_b = make_id("Some Chapter", "concept", "photosynthesis")
    assert id_a == id_b

    urn_a = make_urn("book:chapter", "concept", "Photosynthesis")
    urn_b = make_urn("book:chapter", "concept", "photosynthesis")
    assert urn_a == urn_b

    # punctuation/whitespace-only variant -- the case that used to slip
    # past a name.lower()-keyed dedup and surface as DuplicateIdError.
    id_c = make_id("Nature and Significance of Management", "concept", "Science vs Art")
    id_d = make_id("Nature and Significance of Management", "concept", "Science vs. Art")
    assert id_c == id_d


def test_concept_registry_dedup_behavior_directly():
    """Behavioral check of the exact dedup algorithm pipeline.py uses
    (mirrors the loop body at the concept_registry site in
    pipeline.process_chapter): two topics mentioning the same concept name
    -- whether they differ only in casing or only in punctuation/
    whitespace -- must collapse into ONE registry record whose `topics`
    list contains both topic ids, never two colliding records."""
    concept_registry = {}

    def register_mention(name, topic_id):
        key = slugify(name)
        existing = concept_registry.get(key)
        if existing is None:
            concept_registry[key] = {
                "id": make_id("Some Chapter", "concept", name),
                "name": name.strip(),
                "topics": [topic_id],
            }
        elif topic_id not in existing["topics"]:
            existing["topics"].append(topic_id)

    register_mention("Photosynthesis", "t1")
    register_mention("photosynthesis", "t2")  # same concept, different topic + casing
    register_mention("Respiration", "t2")

    assert len(concept_registry) == 2
    photo = concept_registry[slugify("Photosynthesis")]
    assert photo["topics"] == ["t1", "t2"]


def test_concept_registry_dedup_collapses_punctuation_variant():
    """The exact upstream bug behind the reported DuplicateIdError: two
    topics mention the same concept with only a punctuation/whitespace
    difference ("Science vs Art" vs "Science vs. Art"). Both must resolve
    to ONE concept_registry record (never two records sharing one id)."""
    concept_registry = {}

    def register_mention(name, topic_id):
        key = slugify(name)
        existing = concept_registry.get(key)
        if existing is None:
            concept_registry[key] = {
                "id": make_id("Nature and Significance of Management", "concept", name),
                "name": name.strip(),
                "topics": [topic_id],
            }
        elif topic_id not in existing["topics"]:
            existing["topics"].append(topic_id)

    register_mention("Science vs Art", "t1")
    register_mention("Science vs. Art", "t2")

    assert len(concept_registry) == 1
    only = next(iter(concept_registry.values()))
    assert only["topics"] == ["t1", "t2"]


# ---------------------------------------------------------------------------
# Schema version migration (Fix 2)
# ---------------------------------------------------------------------------

def test_schema_version_was_bumped_to_major_2():
    """TopicNode.concepts' meaning change (names -> canonical ids, same
    field name/shape) is a breaking (MAJOR) change per config.SCHEMA_VERSION's
    documented policy -- a consumer on the old version would silently
    misread the new data rather than erroring. 1.0.0 -> 2.0.0."""
    assert config.SCHEMA_VERSION == "2.0.0"
    major = int(config.SCHEMA_VERSION.split(".")[0])
    assert major >= 2


def test_schema_version_defaults_are_in_sync_across_models():
    """The Pydantic fallback defaults (only hit if canonical_fields()/
    json_writer isn't the one constructing the object) must not silently
    drift from config.SCHEMA_VERSION and report a stale version."""
    assert CanonicalObjectBase.model_fields["schema_version"].default == config.SCHEMA_VERSION
    assert ChapterJSON.model_fields["schema_version"].default == config.SCHEMA_VERSION
    assert EducationalObjectsDocument.model_fields["schema_version"].default == config.SCHEMA_VERSION


def test_migration_is_documented():
    """Fix 2 requires the migration to be clearly documented. MIGRATIONS.md
    must exist at the repo root and describe the 1.0.0 -> 2.0.0 change."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_path = os.path.join(repo_root, "MIGRATIONS.md")
    assert os.path.isfile(migrations_path), "MIGRATIONS.md must exist and document schema_version bumps"

    with open(migrations_path, encoding="utf-8") as f:
        contents = f.read()

    assert "1.0.0" in contents and "2.0.0" in contents
    assert "TopicNode.concepts" in contents
    assert "concept_names" in contents  # the documented migration path for display names


def test_topic_node_concepts_field_name_and_shape_unchanged():
    """Fix 2 explicitly requires: do NOT change field names, do NOT change
    JSON layout -- only the version/documentation. `concepts` must still be
    the field name and still be a List[str] (ids now, not names, but same
    shape)."""
    import typing
    from schemas.chapter_schema import TopicNode
    field = TopicNode.model_fields["concepts"]
    assert typing.get_origin(field.annotation) is list
    assert typing.get_args(field.annotation) == (str,)