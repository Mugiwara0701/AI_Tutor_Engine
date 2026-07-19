"""
modules/educational_taxonomy/catalog.py — M5.2A: the built-in
canonical educational object types that seed `registry.default_taxonomy`.

This module defines *data*, not logic: one `EducationalObjectType` per
canonical object kind, grouped under the seven `EducationalCategory`
values. Nothing here is subject-specific (no `PhysicsObject`,
`MathObject`, ...) and nothing here processes, recognizes, or extracts
anything — it only names and describes the universal vocabulary a
later milestone's concrete processors (M5.2C+) and subject profiles
(M5.2B) will build on.

Extensibility: adding a new built-in type is a pure addition to
`_BUILTIN_TYPES` below (or, for a caller outside this package, a
`registry.register(EducationalObjectType(...))` call against
`default_taxonomy` directly) — it never requires changing
`models.py`, `registry.py`, or any existing entry.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.models import EducationalObjectType

if TYPE_CHECKING:
    from modules.educational_taxonomy.registry import TaxonomyRegistry


def _t(key: str, category: EducationalCategory, display_name: str, description: str) -> EducationalObjectType:
    return EducationalObjectType(
        key=key,
        category=category,
        display_name=display_name,
        description=description,
    )


_BUILTIN_TYPES: Tuple[EducationalObjectType, ...] = (
    # -- Knowledge Objects --------------------------------------------------
    _t("concept", EducationalCategory.KNOWLEDGE, "Concept",
       "A named idea or mental construct a learner is expected to understand."),
    _t("definition", EducationalCategory.KNOWLEDGE, "Definition",
       "A precise statement of the meaning of a term."),
    _t("fact", EducationalCategory.KNOWLEDGE, "Fact",
       "A discrete, verifiable statement presented as established knowledge."),
    _t("law", EducationalCategory.KNOWLEDGE, "Law",
       "A statement describing an invariant relationship, typically empirically established."),
    _t("principle", EducationalCategory.KNOWLEDGE, "Principle",
       "A fundamental proposition that underlies other reasoning or rules."),
    _t("theorem", EducationalCategory.KNOWLEDGE, "Theorem",
       "A proposition formally established as true from prior statements."),
    _t("hypothesis", EducationalCategory.KNOWLEDGE, "Hypothesis",
       "A proposed explanation offered for testing or further reasoning."),
    _t("rule", EducationalCategory.KNOWLEDGE, "Rule",
       "A prescriptive statement governing how something is done or applied."),
    _t("observation", EducationalCategory.KNOWLEDGE, "Observation",
       "A recorded outcome of watching or measuring a phenomenon."),
    _t("postulate", EducationalCategory.KNOWLEDGE, "Postulate",
       "A statement accepted as true without proof, as a starting point for reasoning."),
    _t("axiom", EducationalCategory.KNOWLEDGE, "Axiom",
       "A self-evident statement accepted as a foundational premise of a system."),
    _t("corollary", EducationalCategory.KNOWLEDGE, "Corollary",
       "A proposition that follows readily from a previously established one."),

    # -- Reasoning Objects --------------------------------------------------
    _t("proof", EducationalCategory.REASONING, "Proof",
       "A logically ordered argument establishing that a statement is true."),
    _t("derivation", EducationalCategory.REASONING, "Derivation",
       "A step-by-step procedure that produces a result from prior statements."),
    _t("explanation", EducationalCategory.REASONING, "Explanation",
       "A description of why or how something is the case."),
    _t("justification", EducationalCategory.REASONING, "Justification",
       "Reasoning offered in support of a claim or step."),
    _t("worked_example", EducationalCategory.REASONING, "Worked Example",
       "A fully solved instance demonstrating how a method or concept is applied."),
    _t("counterexample", EducationalCategory.REASONING, "Counterexample",
       "An instance offered to show that a general claim does not always hold."),

    # -- Visual Objects --------------------------------------------------
    _t("figure", EducationalCategory.VISUAL, "Figure",
       "A labelled visual asset presented to support understanding."),
    _t("diagram", EducationalCategory.VISUAL, "Diagram",
       "A schematic visual representation of a structure, process, or relationship."),
    _t("illustration", EducationalCategory.VISUAL, "Illustration",
       "A pictorial visual asset primarily supporting narrative or descriptive content."),
    _t("graph", EducationalCategory.VISUAL, "Graph",
       "A visual plotting one or more quantities against another."),
    _t("map", EducationalCategory.VISUAL, "Map",
       "A visual representation of spatial or geographic information."),
    _t("timeline", EducationalCategory.VISUAL, "Timeline",
       "A visual representation of events ordered along a time axis."),
    _t("flowchart", EducationalCategory.VISUAL, "Flowchart",
       "A visual representation of a sequence of steps or decisions."),
    _t("tree_diagram", EducationalCategory.VISUAL, "Tree Diagram",
       "A visual representation of hierarchical or branching relationships."),
    _t("mind_map", EducationalCategory.VISUAL, "Mind Map",
       "A visual representation radiating related ideas from a central concept."),

    # -- Structured Objects --------------------------------------------------
    _t("table", EducationalCategory.STRUCTURED, "Table",
       "Information organized into rows and columns."),
    _t("matrix", EducationalCategory.STRUCTURED, "Matrix",
       "A rectangular grid of values or entries."),
    _t("comparison", EducationalCategory.STRUCTURED, "Comparison",
       "Content structured to contrast two or more items along shared attributes."),
    _t("classification", EducationalCategory.STRUCTURED, "Classification",
       "Content structured to group items into categories by shared properties."),
    _t("list", EducationalCategory.STRUCTURED, "List",
       "An ordered or unordered enumeration of items."),

    # -- Learning Objects --------------------------------------------------
    _t("activity", EducationalCategory.LEARNING, "Activity",
       "A hands-on task a learner is directed to carry out."),
    _t("experiment", EducationalCategory.LEARNING, "Experiment",
       "A structured procedure carried out to test or observe something."),
    _t("exercise", EducationalCategory.LEARNING, "Exercise",
       "A task set for a learner to practice a skill or apply a concept."),
    _t("practice", EducationalCategory.LEARNING, "Practice",
       "Repetition-oriented content intended to reinforce a skill or concept."),
    _t("project", EducationalCategory.LEARNING, "Project",
       "An extended, often open-ended task producing a tangible outcome."),
    _t("summary", EducationalCategory.LEARNING, "Summary",
       "A condensed restatement of preceding content."),
    _t("note", EducationalCategory.LEARNING, "Note",
       "A short supplementary remark set apart from the main content."),
    _t("warning", EducationalCategory.LEARNING, "Warning",
       "Content flagging a caution, risk, or common error to avoid."),
    _t("important_box", EducationalCategory.LEARNING, "Important Box",
       "Content visually set apart as especially significant."),

    # -- Assessment Objects --------------------------------------------------
    _t("mcq", EducationalCategory.ASSESSMENT, "MCQ",
       "A question with a fixed set of candidate answers, exactly one (or more) correct."),
    _t("assertion_reason", EducationalCategory.ASSESSMENT, "Assertion-Reason",
       "A two-part item pairing an assertion with a reason for evaluation."),
    _t("fill_in_the_blanks", EducationalCategory.ASSESSMENT, "Fill in the Blanks",
       "An item requiring a learner to supply missing word(s) or value(s)."),
    _t("match_the_following", EducationalCategory.ASSESSMENT, "Match the Following",
       "An item requiring a learner to pair items from two related lists."),
    _t("true_false", EducationalCategory.ASSESSMENT, "True/False",
       "An item requiring a learner to judge a statement's veracity."),
    _t("short_answer", EducationalCategory.ASSESSMENT, "Short Answer",
       "A question expecting a brief, direct response."),
    _t("long_answer", EducationalCategory.ASSESSMENT, "Long Answer",
       "A question expecting an extended, multi-part response."),
    _t("hots", EducationalCategory.ASSESSMENT, "HOTS",
       "A Higher Order Thinking Skills question requiring analysis or synthesis beyond recall."),
    _t("case_study", EducationalCategory.ASSESSMENT, "Case Study",
       "An assessment item built around a scenario requiring applied reasoning."),

    # -- Language Objects --------------------------------------------------
    _t("story", EducationalCategory.LANGUAGE, "Story",
       "A narrative prose passage."),
    _t("poem", EducationalCategory.LANGUAGE, "Poem",
       "A composition in verse."),
    _t("dialogue", EducationalCategory.LANGUAGE, "Dialogue",
       "A passage structured as conversational exchange between speakers."),
    _t("literary_device", EducationalCategory.LANGUAGE, "Literary Device",
       "A named technique used in composing or analysing a literary text."),
    _t("grammar_rule", EducationalCategory.LANGUAGE, "Grammar Rule",
       "A prescriptive statement governing correct language usage."),
    _t("paragraph", EducationalCategory.LANGUAGE, "Paragraph",
       "A self-contained block of prose developing a single idea."),
    _t("verse", EducationalCategory.LANGUAGE, "Verse",
       "A single metrical line or short unit of a poem."),
    _t("stanza", EducationalCategory.LANGUAGE, "Stanza",
       "A grouped set of verse lines forming a unit of a poem."),
)


def seed(registry: "TaxonomyRegistry") -> None:
    """Registers every built-in type in `_BUILTIN_TYPES` into
    `registry`. Called once, by `registry.py`, against the module-level
    `default_taxonomy`. Kept as an explicit function (rather than
    reaching into `registry.default_taxonomy` from this module
    directly) so this module has no import-order dependency on
    `registry.py` and stays trivially reusable against any
    `TaxonomyRegistry` instance — e.g. a test building an isolated
    registry pre-seeded with the same built-in catalog."""
    for object_type in _BUILTIN_TYPES:
        registry.register(object_type)


__all__ = [
    "seed",
]
