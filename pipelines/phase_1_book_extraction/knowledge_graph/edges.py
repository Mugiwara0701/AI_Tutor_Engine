"""
knowledge_graph/edges.py — Phase C2 Task 1: concrete Graph Edge classes.

SCOPE: this module defines one thin dataclass subclass of `GraphEdgeBase`
per DETERMINISTIC relationship type Phase B3 (`compiler/relationships.py`)
already produces -- `compiler.relationships.RELATIONSHIP_TYPES`
("has_definition", "explains", "described_by", "contains", "appears_in",
"belongs_to", "uses_concept", "illustrates", "teaches"; nine types),
adding NO new fields. This mirrors `knowledge_graph/nodes.py`'s own
precedent for Phase C1 node types exactly -- same "isinstance()-checkable
identity, one stable importable symbol per type, no new fields" reasoning
(see that module's own docstring) -- and, one layer further back,
`compiler/registries.py`'s own per-type registry precedent.

WHY ONLY NINE CLASSES, NOT ALL TWELVE `FUTURE_EDGE_TYPES`: `edge.py`'s
own `FUTURE_EDGE_TYPES` additionally lists "prerequisite", "depends_on",
and "related_to" -- three semantic/educational edge types no frozen
compiler phase deterministically produces yet (see that module's own
docstring: those three belong to the "semantic/educational" family,
distinct from the "structural/compositional" + Phase-B3-sourced types
this module implements). Per this phase's own Task 1 instruction ("Edge
classes should represent the deterministic relationship types already
produced by Phase B3") and DO-NOT-IMPLEMENT list ("Do NOT implement
prerequisite reasoning", "Do NOT implement dependency analysis"), this
module deliberately implements a concrete class for only the nine types
`compiler.relationships.RELATIONSHIP_TYPES` already names -- see the
assertion at the bottom of this module, which checks exactly this set,
not `FUTURE_EDGE_TYPES`. Adding "prerequisite"/"depends_on"/"related_to"
concrete classes is future work for whichever phase first gives one of
them a deterministic source.

WHY `EDGE_TYPE` IS A CLASS VAR, NOT A DATACLASS FIELD: identical
reasoning to `knowledge_graph/nodes.py`'s own `NODE_TYPE` -- see that
module's docstring's "WHY NO NEW FIELDS, AND WHY `NODE_TYPE` IS A CLASS
VAR" section, which applies here verbatim with `EDGE_TYPE`/`GraphEdgeBase`
substituted for `NODE_TYPE`/`GraphNodeBase`. `GraphEdgeBase` (edge.py)
declares several required fields after `edge_type` in field order
(`source_node_id`, `target_node_id`, ...), so a subclass cannot give
`edge_type` a default without forcing every later field to grow a bogus
default too; a plain `ClassVar[str]` sidesteps that entirely, and the
Edge Builder (`knowledge_graph/build_edges.py`) passes
`edge_type=<cls>.EDGE_TYPE` explicitly at construction time.

WHY NOT A SECOND BASE CLASS: every class below inherits directly from
`GraphEdgeBase` (`knowledge_graph.edge`) and nothing else -- per this
phase's own Task 1 instruction ("Reuse GraphEdgeBase. Do NOT introduce
another base class."). No class here overrides `to_dict()` or any other
`GraphEdgeBase` method.

DIRECTED: every one of these nine types is a directed, asymmetric
relationship (e.g. Concept --has_definition--> Definition is not the
same statement as Definition --has_definition--> Concept) -- so every
class below simply relies on `GraphEdgeBase.directed`'s own base default
(`True`) rather than overriding it. None of the (not-yet-implemented)
symmetric future types like "related_to" are defined here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, Type

from compiler.relationships import RELATIONSHIP_TYPES
from .edge import GraphEdgeBase


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
EDGE_CLASSES_VERSION = "C2.0"


@dataclass
class HasDefinitionEdge(GraphEdgeBase):
    """Concept --has_definition--> Definition (compiler/relationships.py
    ::_generate_definition_concept_relationships)."""

    EDGE_TYPE: ClassVar[str] = "has_definition"


@dataclass
class ExplainsEdge(GraphEdgeBase):
    """Glossary Entry --explains--> Concept
    (compiler/relationships.py::_generate_glossary_concept_relationships)."""

    EDGE_TYPE: ClassVar[str] = "explains"


@dataclass
class DescribedByEdge(GraphEdgeBase):
    """Concept --described_by--> Glossary Entry
    (compiler/relationships.py::_generate_glossary_concept_relationships)."""

    EDGE_TYPE: ClassVar[str] = "described_by"


@dataclass
class ContainsEdge(GraphEdgeBase):
    """Topic --contains--> Concept
    (compiler/relationships.py::_generate_topic_concept_relationships)."""

    EDGE_TYPE: ClassVar[str] = "contains"


@dataclass
class AppearsInEdge(GraphEdgeBase):
    """Concept --appears_in--> Topic
    (compiler/relationships.py::_generate_appears_in_and_belongs_to_relationships)."""

    EDGE_TYPE: ClassVar[str] = "appears_in"


@dataclass
class BelongsToEdge(GraphEdgeBase):
    """Definition --belongs_to--> Topic, Glossary Entry --belongs_to-->
    Topic (compiler/relationships.py::
    _generate_appears_in_and_belongs_to_relationships)."""

    EDGE_TYPE: ClassVar[str] = "belongs_to"


@dataclass
class UsesConceptEdge(GraphEdgeBase):
    """Equation --uses_concept--> Concept
    (compiler/relationships.py::_generate_concept_ids_relationships)."""

    EDGE_TYPE: ClassVar[str] = "uses_concept"


@dataclass
class IllustratesEdge(GraphEdgeBase):
    """Figure / Diagram / Table --illustrates--> Concept
    (compiler/relationships.py::_generate_concept_ids_relationships)."""

    EDGE_TYPE: ClassVar[str] = "illustrates"


@dataclass
class TeachesEdge(GraphEdgeBase):
    """Activity --teaches--> Concept
    (compiler/relationships.py::_generate_concept_ids_relationships)."""

    EDGE_TYPE: ClassVar[str] = "teaches"


# --------------------------------------------------------------------------
# relationship type -> concrete class, in the same order
# compiler.relationships.RELATIONSHIP_TYPES already declares -- the Edge
# Builder (knowledge_graph/build_edges.py) imports this rather than
# re-listing every class itself, so there is exactly one place that maps
# a relationship type string to the class that represents it as a graph
# edge (mirrors knowledge_graph/nodes.py's own NODE_CLASSES precedent).
# --------------------------------------------------------------------------
EDGE_CLASSES: Dict[str, Type[GraphEdgeBase]] = {
    HasDefinitionEdge.EDGE_TYPE: HasDefinitionEdge,
    ExplainsEdge.EDGE_TYPE: ExplainsEdge,
    DescribedByEdge.EDGE_TYPE: DescribedByEdge,
    ContainsEdge.EDGE_TYPE: ContainsEdge,
    AppearsInEdge.EDGE_TYPE: AppearsInEdge,
    BelongsToEdge.EDGE_TYPE: BelongsToEdge,
    UsesConceptEdge.EDGE_TYPE: UsesConceptEdge,
    IllustratesEdge.EDGE_TYPE: IllustratesEdge,
    TeachesEdge.EDGE_TYPE: TeachesEdge,
}

# Sanity fact this module's own tests assert: every relationship type
# Phase B3 (compiler.relationships.RELATIONSHIP_TYPES) already produces
# now has exactly one concrete class here, and vice versa -- no type left
# unimplemented, no class added for a type Phase B3 doesn't (yet)
# produce. Deliberately checked against RELATIONSHIP_TYPES, NOT against
# edge.py's own (broader) FUTURE_EDGE_TYPES -- see module docstring's
# "WHY ONLY NINE CLASSES" section.
assert set(EDGE_CLASSES) == set(RELATIONSHIP_TYPES), (
    "knowledge_graph.edges.EDGE_CLASSES must define exactly one concrete "
    "class per compiler.relationships.RELATIONSHIP_TYPES entry"
)