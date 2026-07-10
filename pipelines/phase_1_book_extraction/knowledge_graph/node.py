"""
knowledge_graph/node.py — Phase C0 Task 2: Graph Node Architecture.
(Phase C0.1 audit-findings refinement: see "C0.1 FIELD EXPANSION" below
for what changed and why.)

SCOPE: this module defines ONLY the base model every future graph node
type (Topic, Concept, Definition, Glossary, Equation, Figure, Diagram,
Table, Activity, Example, Box, Warning, Note, ...) will eventually
inherit from -- mirrors schemas/canonical_base.py's own relationship to
its future subclasses exactly (that module's own docstring: "This
introduces the common parent schema... It does NOT migrate any existing
schema... that migration is later work"). No concrete node subclass is
defined here. No node instance is ever constructed anywhere in this
codebase as of Phase C0.

WHY A NODE WRAPS, RATHER THAN IS, A CANONICAL OBJECT: `GraphNodeBase`
holds a `compiler_object_id` / `compiler_object_urn` /
`compiler_object_type` / `compiler_registry` quartet pointing back at
the Compiler IR item this node represents, rather than embedding that
item's fields directly. This is the same "describes, does not duplicate
or mutate" relationship every Phase B5 artifact already has to the
registries it reads (see compiler/build.py's own module docstring:
"reads already-computed compiler state ... never generates, repairs, or
mutates a single field"). A Knowledge Graph node is a graph-shaped VIEW
over a canonical object, not a copy of one -- so if C1 later needs the
object's own fields beyond the small, denormalized convenience fields
below, it reads them from Compiler IR via `compiler_registry`/
`compiler_object_id`, never by GraphNodeBase caching a snapshot that
could drift out of sync.

C0.1 FIELD EXPANSION (audit-findings refinement): an independent
architecture audit of Phase C0 found that GraphNodeBase, as originally
implemented, was missing several fields Phase C1 will need on every
node. Two kinds of gaps were found and resolved here, additively, with
no other change to this module's shape or philosophy:

  1. RENAMED for clarity, same meaning: `source_object_id` ->
     `compiler_object_id`, `source_object_type` -> `compiler_object_type`,
     `source_registry` -> `compiler_registry`. These three already
     existed in Phase C0 and already carried exactly this information;
     the audit found the `source_*` naming ambiguous next to the new
     `compiler_object_urn`/`compiler_version` fields below (a reader
     could otherwise mistake "source" for something upstream of the
     compiler, e.g. the PDF page). Renaming, not adding a parallel set
     of fields, keeps this base class free of duplicate fields carrying
     the same meaning. Safe to rename outright: no concrete node
     subclass exists yet and no node is ever instantiated anywhere in
     this codebase (Phase C0), so there is no call site to migrate.
  2. GENUINELY NEW, not previously present in any form:
     `compiler_object_urn`, `display_name`, `provenance`,
     `compiler_version`. See FIELD NOTES below for what each holds and
     where it comes from on the wrapped canonical object.

The design philosophy is unchanged: Graph Nodes wrap Compiler IR; Graph
Nodes do NOT duplicate Compiler IR. The four `compiler_object_*`/
`compiler_registry` fields are pure pointers (never authoritative
data); `display_name`/`provenance`/`compiler_version` are small,
deliberately denormalized READ-ONLY convenience copies of three fields
the wrapped canonical object already carries (its own name/term/title,
its own `provenance` dict, and its own
`creation_metadata.compiler_version`) -- provided directly on the node
so a graph consumer can display or filter by them without a second
Compiler IR lookup per node, exactly the same tradeoff
schemas/canonical_base.py's own `CanonicalObjectBase` already makes by
carrying `provenance`/`compiler_version` itself rather than forcing
every reader to dereference somewhere else. These three remain
snapshots, not the source of truth: `compiler_registry`/
`compiler_object_id` are what a future phase re-reads from Compiler IR
if it needs anything beyond this convenience trio. No other field was
added, and no second base node class or inheritance change was made.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


# --------------------------------------------------------------------------
# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION constant in this package. Bump only if
# GraphNodeBase's own field set changes shape.
# --------------------------------------------------------------------------
NODE_SCHEMA_VERSION = "C0.1"


# --------------------------------------------------------------------------
# Future node types (Task 2's own "Examples of future node types" list).
# Declared here, as a closed-set-so-far constant, purely so C1's own
# node-type registration has one canonical place to extend rather than a
# free-form string scattered across call sites -- mirrors
# compiler/relationships.py's own `RELATIONSHIP_TYPES` list precedent
# (declared once, referenced everywhere else). NOT used to construct
# anything in Phase C0 -- no NodeType subclass exists yet, and nothing
# in this codebase currently instantiates a node of any of these types.
# --------------------------------------------------------------------------
FUTURE_NODE_TYPES = (
    "topic",
    "concept",
    "definition",
    "glossary",
    "equation",
    "figure",
    "diagram",
    "table",
    "activity",
    "example",
    "box",
    "warning",
    "note",
)


@dataclass
class GraphNodeBase:
    """Base model every future concrete graph node type inherits from.

    Every future node type (see FUTURE_NODE_TYPES) is expected to
    subclass this dataclass and add only the fields specific to that
    node's own educational role (mirrors CanonicalObjectBase's own
    "shared metadata declared once" rationale) -- see this module's own
    docstring for the full reasoning. No subclass is defined in Phase
    C0; this is architecture only.

    FIELD NOTES:
    - `node_id` / `node_urn`: built by
      knowledge_graph.identity.node_id()/node_urn() -- never
      hand-assigned by a subclass.
    - `node_type`: one of FUTURE_NODE_TYPES once a concrete subclass
      exists; kept as a plain `str` here (not an enum) so a future node
      type can be added without editing this base class, the same
      "additive, don't touch the base" property CanonicalObjectBase's
      `object_type: str` field already has relative to
      schemas/educational_objects_schema.py's own concrete object
      types.
    - `compiler_object_id` / `compiler_object_urn` /
      `compiler_object_type` / `compiler_registry`: the Compiler IR
      item this node represents -- see module docstring's WHY A NODE
      WRAPS section. `compiler_object_id`/`compiler_object_urn` are the
      wrapped canonical object's own `id`/`urn` (see
      compiler/registries.py's module docstring: every canonical
      object dict already carries both, unconditionally).
      `compiler_registry` is one of compiler.registries.REGISTRY_NAMES
      once a concrete node is built (renamed from this field's Phase C0
      name, `source_registry` -- see this module's own "C0.1 FIELD
      EXPANSION" docstring section for why).
    - `display_name`: a read-only, denormalized copy of the wrapped
      canonical object's own human-readable label (its `name` for a
      Concept, `term` for a Definition/Glossary entry, `title` for a
      Figure/Diagram/Table/Activity/Box/Example, ...) -- added in the
      C0.1 refinement so a graph consumer can show/sort/filter nodes
      without a Compiler IR lookup per node. `Optional[str]`, not
      required: some wrapped object types (see
      compiler/registries.py's own `name_of` discussion) may not have
      one.
    - `provenance`: a read-only, denormalized COPY of the wrapped
      canonical object's own `provenance` dict (schemas/canonical_base.py
      ::Provenance, serialized) -- never re-derived, never mutated here;
      added in the C0.1 refinement for the same "no second lookup per
      node" reason as `display_name`. `Optional[Dict[str, Any]]`: `None`
      until a concrete node is actually built from a real canonical
      object.
    - `compiler_version`: a read-only, denormalized copy of the wrapped
      canonical object's own `creation_metadata.compiler_version` --
      added in the C0.1 refinement. Distinct from `node_schema_version`
      below (this module's own schema version) and from
      knowledge_graph.schema.KnowledgeGraphMetadata's own
      `source_compiler_version` (that field describes an entire graph
      build; this one describes only the one wrapped object this node
      represents).
    - `graph_id` / `graph_urn`: which Knowledge Graph build (see
      knowledge_graph.schema.KnowledgeGraphMetadata) this node belongs
      to -- lets a node be unambiguous even if serialized outside its
      owning graph's own context.
    - `node_schema_version`: this module's own NODE_SCHEMA_VERSION,
      stamped per-instance the same way every Compiler IR item already
      stamps its own `schema_version` (schemas/canonical_base.py).
    - `metadata`: an open, `extra`-shaped bag for whatever a concrete
      node type needs beyond the shared fields above -- mirrors
      CanonicalObjectBase's own `model_config = ConfigDict(extra="allow")`
      escape hatch, expressed as an explicit dict field here since this
      is a plain dataclass, not a pydantic model (kept deliberately
      framework-light, matching compiler/build.py's own dataclass
      choice over pydantic for compiler-internal artifacts, as opposed
      to schema-layer artifacts like CanonicalObjectBase).
    """

    node_id: str
    node_urn: str
    node_type: str
    graph_id: str
    graph_urn: str
    compiler_object_id: str
    compiler_object_urn: str
    compiler_object_type: str
    compiler_registry: str
    display_name: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    compiler_version: Optional[str] = None
    node_schema_version: str = NODE_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_known_future_node_type(node_type: str) -> bool:
    """Pure membership check against FUTURE_NODE_TYPES -- provided so a
    future C1 node builder can validate a node type without duplicating
    this list. Does not construct or register anything."""
    return node_type in FUTURE_NODE_TYPES