"""
knowledge_graph/nodes.py — Phase C1 Task 2: concrete Graph Node classes.

SCOPE: this module defines the thirteen concrete node types Phase C0's
`knowledge_graph.node.FUTURE_NODE_TYPES` already named as future work
(topic, concept, definition, glossary, equation, figure, diagram, table,
activity, example, box, warning, note) -- one thin dataclass subclass of
`GraphNodeBase` per type, adding NO new fields. This mirrors
`compiler/registries.py`'s own per-type registry precedent (ConceptRegistry,
FigureRegistry, ... -- "each ... does nothing but fix `name=` in its
constructor", kept for isinstance()-checkable identity and a stable,
importable symbol per type -- see that module's own "ARCHITECTURAL
DECISION LOG" section for the exact reasoning this follows).

WHY NO NEW FIELDS, AND WHY `NODE_TYPE` IS A CLASS VAR, NOT A DATACLASS
FIELD: `GraphNodeBase.node_type` (a required, no-default field) already
carries a node's type as *data* -- see node.py. A concrete subclass could
try to give `node_type` a fixed default value instead of leaving every
node.py field as-is, but `GraphNodeBase` declares several OTHER required
fields (`compiler_object_id`, `compiler_object_urn`, ...) positioned
after `node_type` in field order; a dataclass cannot give one field a
default while a later field in the same inheritance chain still has
none (Python raises at class-definition time: "non-default argument
follows default argument"). Rather than force every one of those later
fields to grow a bogus default just to make `node_type` defaultable too
-- which would silently make a required field optional-looking -- each
node subclass instead exposes its fixed type as a plain class attribute,
`NODE_TYPE: ClassVar[str]` (excluded from the dataclass's own `__init__`
by `ClassVar`, per the dataclasses stdlib contract), and the Node
Builder (`knowledge_graph/build_nodes.py`) passes
`node_type=<cls>.NODE_TYPE` explicitly at construction time. Every
`GraphNodeBase` field therefore stays exactly as required/optional as
Phase C0 already declared it -- no shape change to the base class, per
this phase's own "do not rewrite existing code" instruction.

WHY NOT A SECOND BASE CLASS: every class below inherits directly from
`GraphNodeBase` (`knowledge_graph.node`) and nothing else -- per this
phase's own Task 2 instruction ("Reuse GraphNodeBase. Do NOT introduce
another base class."). No class here overrides `to_dict()` or any other
`GraphNodeBase` method.

NAMING NOTE: `schemas/chapter_schema.py` already defines an unrelated
`TopicNode` (a Chapter-JSON-shaped Pydantic model describing one topic
entry in Chapter JSON -- an Educational JSON artifact). This module's
own `TopicNode` is a different type in a different package
(`knowledge_graph.nodes.TopicNode`, a Knowledge Graph node wrapping a
canonical Topic object) and the two are never imported into the same
namespace unqualified anywhere in this codebase. See
`knowledge_graph/node.py`'s own "WHY A NODE WRAPS, RATHER THAN IS, A
CANONICAL OBJECT" section for why a graph node is never the same object
as -- or a replacement for -- the Educational JSON shape it is built
from.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, Type

from .node import FUTURE_NODE_TYPES, GraphNodeBase


# --------------------------------------------------------------------------
# This module's own version marker.
# --------------------------------------------------------------------------
NODE_CLASSES_VERSION = "C1.0"


@dataclass
class TopicNode(GraphNodeBase):
    """Wraps one canonical Topic object (`compiler.registries.TopicRegistry`
    item -- a canonical-enveloped copy of `pipeline.py`'s own `topics_out`
    entry; see that registry's own docstring)."""

    NODE_TYPE: ClassVar[str] = "topic"


@dataclass
class ConceptNode(GraphNodeBase):
    """Wraps one canonical Concept object
    (`compiler.registries.ConceptRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "concept"


@dataclass
class DefinitionNode(GraphNodeBase):
    """Wraps one canonical Definition object
    (`compiler.registries.DefinitionRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "definition"


@dataclass
class GlossaryNode(GraphNodeBase):
    """Wraps one canonical Glossary-entry object
    (`compiler.registries.GlossaryRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "glossary"


@dataclass
class EquationNode(GraphNodeBase):
    """Wraps one canonical Equation object
    (`compiler.registries.EquationRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "equation"


@dataclass
class FigureNode(GraphNodeBase):
    """Wraps one canonical Figure object
    (`compiler.registries.FigureRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "figure"


@dataclass
class DiagramNode(GraphNodeBase):
    """Wraps one canonical Diagram object
    (`compiler.registries.DiagramRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "diagram"


@dataclass
class TableNode(GraphNodeBase):
    """Wraps one canonical Table object
    (`compiler.registries.TableRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "table"


@dataclass
class ActivityNode(GraphNodeBase):
    """Wraps one canonical Activity object
    (`compiler.registries.ActivityRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "activity"


@dataclass
class ExampleNode(GraphNodeBase):
    """Wraps one canonical Example object
    (`compiler.registries.ExampleRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "example"


@dataclass
class BoxNode(GraphNodeBase):
    """Wraps one canonical Box object
    (`compiler.registries.BoxRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "box"


@dataclass
class WarningNode(GraphNodeBase):
    """Wraps one canonical Warning object
    (`compiler.registries.WarningRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "warning"


@dataclass
class NoteNode(GraphNodeBase):
    """Wraps one canonical Note object
    (`compiler.registries.NoteRegistry` item)."""

    NODE_TYPE: ClassVar[str] = "note"


# --------------------------------------------------------------------------
# node_type -> concrete class, in the same order node.py's own
# FUTURE_NODE_TYPES already declares -- the Node Builder
# (knowledge_graph/build_nodes.py) imports this rather than re-listing
# every class itself, so there is exactly one place that maps a node
# type string to the class that represents it.
# --------------------------------------------------------------------------
NODE_CLASSES: Dict[str, Type[GraphNodeBase]] = {
    TopicNode.NODE_TYPE: TopicNode,
    ConceptNode.NODE_TYPE: ConceptNode,
    DefinitionNode.NODE_TYPE: DefinitionNode,
    GlossaryNode.NODE_TYPE: GlossaryNode,
    EquationNode.NODE_TYPE: EquationNode,
    FigureNode.NODE_TYPE: FigureNode,
    DiagramNode.NODE_TYPE: DiagramNode,
    TableNode.NODE_TYPE: TableNode,
    ActivityNode.NODE_TYPE: ActivityNode,
    ExampleNode.NODE_TYPE: ExampleNode,
    BoxNode.NODE_TYPE: BoxNode,
    WarningNode.NODE_TYPE: WarningNode,
    NoteNode.NODE_TYPE: NoteNode,
}

# Sanity fact this module's own tests assert: every node type node.py
# already reserved (FUTURE_NODE_TYPES) now has exactly one concrete
# class here, and vice versa -- no type left unimplemented, no class
# added for a type node.py doesn't know about.
assert set(NODE_CLASSES) == set(FUTURE_NODE_TYPES), (
    "knowledge_graph.nodes.NODE_CLASSES must define exactly one concrete "
    "class per knowledge_graph.node.FUTURE_NODE_TYPES entry"
)