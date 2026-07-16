"""document_structure_tree/tests/fixtures.py — small, hand-built
fixtures shared across this milestone's test modules. Builds only on
already-frozen, earlier-milestone public API (`build_tree`,
`InMemoryCanonicalRegistrySnapshot`); no new tree-assembly or
validation logic lives here.
"""
from __future__ import annotations

from document_structure_tree import (
    CanonicalObjectId,
    ChapterId,
    CompilerVersion,
    ContentRef,
    HeadingSource,
    InMemoryCanonicalRegistrySnapshot,
    ObjectType,
    ROOT_CONTENT_KEY,
    SchemaVersion,
    Timestamp,
    build_tree,
)

CHAPTER_ID = ChapterId("chap-07")
OTHER_CHAPTER_ID = ChapterId("chap-08")
SCHEMA_VERSION = SchemaVersion("1.1.0")
COMPILER_VERSION = CompilerVersion("0.1.0")
REGISTRY_REF = "registry-snap-2026-07-01"
BUILD_TIMESTAMP = Timestamp("2026-07-15T09:00:00Z")


def small_clean_headings():
    """Two top-level numbered headings, one nested numbered heading --
    every `node_id` disambiguated by `number` (Tier 1, architecture
    §14), so this fixture's identity is stable across rebuilds by
    construction."""
    return [
        HeadingSource(
            id="h1", parent_id=None, number="4.1",
            title="Newton's Second Law", reading_order=0,
        ),
        HeadingSource(
            id="h2", parent_id=None, number="4.2",
            title="Applications", reading_order=1,
        ),
        HeadingSource(
            id="h1a", parent_id="h1", number="4.1.1",
            title="Derivation", reading_order=0,
        ),
    ]


def small_clean_content_by_heading():
    """One content object owned by the chapter root directly, one
    owned by a nested heading -- exercises both root-owned content
    (architecture §17, "Content preceding the first heading ... is
    owned by the chapter root") and ordinary nested ownership."""
    return {
        ROOT_CONTENT_KEY: [
            ContentRef(object_id="obj-441", object_type="paragraph_group", page=88, position=0.0),
        ],
        "h1a": [
            ContentRef(object_id="obj-442", object_type="definition", page=89, position=0.0),
        ],
    }


def build_small_clean_tree():
    """The `BuiltTree` (roadmap M2 output) this milestone's tests
    generate artifacts from."""
    return build_tree(CHAPTER_ID, small_clean_headings(), small_clean_content_by_heading())


def clean_registry(chapter_id: ChapterId = CHAPTER_ID) -> InMemoryCanonicalRegistrySnapshot:
    """A `CanonicalRegistrySnapshot` (Milestone 3) that agrees exactly
    with `small_clean_content_by_heading()`'s two content objects --
    every R2/R3/R4/B2 check should pass against it."""
    return InMemoryCanonicalRegistrySnapshot(
        object_types={
            CanonicalObjectId("obj-441"): ObjectType("paragraph_group"),
            CanonicalObjectId("obj-442"): ObjectType("definition"),
        },
        chapter_objects={
            chapter_id: frozenset({CanonicalObjectId("obj-441"), CanonicalObjectId("obj-442")}),
        },
    )


def empty_registry(chapter_id: ChapterId = CHAPTER_ID) -> InMemoryCanonicalRegistrySnapshot:
    """A resolvable registry snapshot (satisfies B2) that owns no
    content objects for `chapter_id` -- useful for a headings-only
    tree with no `content`-type sequence entries at all, where R4
    should still pass vacuously (no unowned objects, since there are
    none)."""
    return InMemoryCanonicalRegistrySnapshot(object_types={}, chapter_objects={chapter_id: frozenset()})