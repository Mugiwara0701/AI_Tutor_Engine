"""
compiler/validation.py — Phase B4: Compiler Validation & Integrity Pass.

SCOPE (read this before touching anything else): Phase A, Phase B0,
Phase B1, Phase B1b, Phase B1c, Phase B2, and Phase B3 are frozen -- this
module does not redesign CanonicalRegistry/RegistryManager (compiler/
registry.py, compiler/registry_manager.py), compiler/state.py's
_CURRENT_REGISTRY_MANAGER lifecycle, compiler/relationships.py's
RelationshipRegistry, compiler/normalization.py, or compiler/
references.py. It also does not touch json_writer.py / schemas/
chapter_schema.py / ChapterJSON. It ONLY adds a fifth, read-only compiler
pass that INSPECTS what every earlier phase already built and reports
what it finds -- it never generates, repairs, or mutates a single field
anywhere in the compiler IR.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not a
repair pass, not a re-normalization pass, not a Knowledge Graph, and not
a relationship/reference generator. Every function in this module is a
pure read: given a RegistryManager (and, optionally, the same `topics`
list resolve_references()/resolve_relationships() were given), it reads
already-computed fields and returns ValidationIssue records describing
what it found. Nothing here ever calls registry.insert()/.update()/
.remove(), ever writes a key onto an existing item's dict, or ever
touches `topics` beyond reading it.

VALIDATION STRATEGY (mirrors every earlier compiler pass's own "reuse,
don't reinvent" rule): every check below reads a field an earlier,
frozen phase already computed -- REGISTRY_NAMES (compiler/registries.py),
REFERENCE_FIELDS / _REVERSE_ID_FIELD (compiler/references.py),
RELATIONSHIP_REGISTRY_NAME / RELATIONSHIP_TYPES / the relationship id
algorithm (compiler/relationships.py) -- rather than redefining a second
copy of any of them. Where this module needs a fact no earlier phase
already exposes (e.g. "does this id look like it came from make_id()"),
it computes that fact by reading existing data only, never by calling
into modules/ or re-deriving anything that would count as generation.

WHAT "VALID" MEANS HERE: a validation rule below produces either an
`error` (something later phases could not safely rely on -- a reference
to a nonexistent object, a missing required field, two objects sharing
an id) or a `warning` (something worth a human's attention but not
necessarily wrong -- e.g. two different concepts whose lookup keys
collapsed to the same normalized string, which Phase B2's own concept
lookup index already defensively tolerates by dropping the ambiguous
key, per compiler/references.py's own documented behavior). Nothing here
decides FOR the compiler whether to proceed; validate_compiler_state()
only reports, via `status: "pass"` (zero errors) or `status: "fail"`
(one or more errors) in the returned report -- what pipeline.py or a
future Phase B5 does with that status is out of this module's scope.

PIPELINE INTEGRATION: validate_compiler_state(manager, *, topics=None,
page_count=None) is the one pipeline.py integration point, mirroring
resolve_references()'s and resolve_relationships()'s own shape exactly.
It must run AFTER compiler.relationships.resolve_relationships() (so the
"relationships" registry already exists and is fully populated to
validate) and BEFORE compiler_state.set_current_registry_manager() (so
validation genuinely inspects "the IR as it will be handed to later
phases", not a stale snapshot) -- see pipeline.py's own integration
comment at the call site. `page_count` is optional (mirrors every other
`topics`-optional check's "checkable if supplied, `not_checked`/skipped
otherwise, never assumed" convention) and is threaded through only to
`_validate_provenance_integrity`, the one check that needs a chapter's
own page range to catch a `source_page` that points outside it.
The returned report is handed to compiler_state.set_current_validation_
report() immediately after (a Phase B4 addition to compiler/state.py --
see that module's own docstring), making it "part of the compiler
state" per the task spec, WITHOUT writing it into ChapterJSON or onto
`manager` itself.

REPORT STRUCTURE: validate_compiler_state() returns a plain dict (see
ValidationReport.to_dict() below) with: `version`, `generated_at`,
`status` ("pass"/"fail"), `errors` (list), `warnings` (list),
`statistics`, `registry_summary`, `reference_summary`,
`relationship_summary`, `integrity_summary`, `hierarchy_summary`,
`topic_linking_summary`, `graph_summary`, `provenance_summary`,
`structural_completeness_summary`. This dict is the compiler
artifact this phase produces -- a diagnostic report, not educational
content, never serialized into Chapter JSON (see module docstring's
"does not touch ... ChapterJSON" line above).

BACKWARD COMPATIBILITY: every id/urn/reference/relationship field this
module reads is only ever read, never changed. No existing registry,
field, or Chapter JSON output changes as a result of this module
existing. The only new compiler artifact is the validation report
itself (plus the two small, additive get/set functions in compiler/
state.py that hold it).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .registry_manager import RegistryManager
from .registries import REGISTRY_NAMES
from .references import REFERENCE_FIELDS, _REVERSE_ID_FIELD
from .relationships import (
    RELATIONSHIP_REGISTRY_NAME,
    RELATIONSHIP_TYPES,
    _relationship_id,
)
from modules.topic_linker import TOPIC_REVERSE_FIELDS

# --------------------------------------------------------------------------
# Static, deterministic constants
# --------------------------------------------------------------------------

# This module's own version marker (independent of every earlier phase's
# own *_VERSION constant, which versions those separate passes). Bump
# only if the validation logic in this file itself changes in a way a
# consumer of `report["version"]` should be able to detect.
VALIDATION_VERSION = "1.0.0"

# Required top-level fields on every canonical object (task's own
# "Canonical Object Integrity" list), per schemas/chapter_schema.py's
# CanonicalObjectBase. `compiler_version` is checked separately (see
# _check_canonical_object below) since it lives one level down, inside
# `creation_metadata`, not as a top-level key.
REQUIRED_CANONICAL_FIELDS: List[str] = [
    "id", "urn", "object_type", "schema_version", "provenance",
    "validation_status",
]

# relationship `source_type`/`target_type` string -> the RegistryManager
# registry name that type's ids live in. "topic" is intentionally absent
# -- topics are not a RegistryManager registry (see compiler/
# references.py's own TOPIC -> CONCEPT RESOLUTION note and compiler/
# relationships.py's own module docstring); a topic-typed source/target
# can only be checked against an optional `topics` argument, never
# against `manager` itself.
_RELATIONSHIP_ENDPOINT_REGISTRY: Dict[str, str] = {
    "concept": "concepts",
    "definition": "definitions",
    "glossary_entry": "glossary",
    "equation": "equations",
    "figure": "figures",
    "diagram": "diagrams",
    "table": "tables",
    "activity": "activities",
}

# --------------------------------------------------------------------------
# MILESTONE 2 additions -- Structural Validation (see module docstring
# addendum below). These constants back the four new validation
# categories (Hierarchy, Topic Linking, Graph Integrity, Provenance) and
# reuse, rather than redefine, facts earlier frozen phases already
# established.
# --------------------------------------------------------------------------

# object_type string (schemas/chapter_schema.py's CanonicalObjectBase.
# object_type, set by modules/canonical.py::canonical_fields()) that a
# well-formed item in a given RegistryManager registry is expected to
# carry. Used only for the "inconsistent object ownership" structural
# check (an item physically stored under, e.g., the "figures" registry
# but whose own object_type says "table") -- never used to move or
# re-key an item. "topics" is intentionally absent: TopicRegistry stores
# a canonical-enveloped *copy* with object_type="topic" (see compiler/
# registries.py's own "TOPIC REGISTRY" docstring section), which this
# module already treats like every other registry for this one check.
OBJECT_TYPE_BY_REGISTRY: Dict[str, str] = {
    "topics": "topic",
    "definitions": "definition",
    "concepts": "concept",
    "glossary": "glossary_entry",
    "figures": "figure",
    "diagrams": "diagram",
    "tables": "table",
    "equations": "equation",
    "activities": "activity",
    "boxes": "box",
    "warnings": "warning",
    "notes": "note",
    "examples": "example",
}

# TOPIC_REVERSE_FIELDS (modules/topic_linker.py, Milestone 1) maps
# object_type -> TopicNode reverse-list field name. For every type this
# module tracks in OBJECT_TYPE_BY_REGISTRY, that reverse-list field name
# is, by construction, identical to the RegistryManager registry name
# the forward-linked object itself lives in (e.g. object_type "figure"
# -> reverse field "figures" -> registry "figures") -- so no separate
# mapping table is needed; this dict simply selects which registries
# have a topic-reverse-list counterpart to cross-check at all (a `None`
# value, e.g. "glossary_entry", means "forward topic_ids is still
# checked elsewhere, but there is no reverse list to reconcile it
# against").
_TOPIC_LINKED_REGISTRIES: List[str] = sorted(
    {
        field
        for object_type, field in TOPIC_REVERSE_FIELDS.items()
        if field is not None and object_type in OBJECT_TYPE_BY_REGISTRY.values()
    }
)

# make_id()'s (modules/pdf_parser.py) and _relationship_id()'s
# (compiler/relationships.py) own output shape: a lowercase slug (never
# empty, alphanumerics/hyphens only, truncated to <=60 chars) followed by
# "-" and a 6-hex-digit sha1 prefix -- no random/UUID/timestamp
# component. Used only as a structural sanity check (see
# _check_id_determinism below): a real id/urn that doesn't match this
# shape is a WARNING (worth a human's attention), not proof of a bug --
# see that function's own docstring for why this is intentionally not an
# error.
_DETERMINISTIC_ID_PATTERN = re.compile(r"^[a-z0-9-]+-[0-9a-f]{6}$")
_DETERMINISTIC_URN_PATTERN = re.compile(r"^urn:[a-z0-9-]+:.+$")


# --------------------------------------------------------------------------
# Report data model
# --------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """One error or warning. `severity` is "error" or "warning".
    `rule` is a short, stable machine-readable name (e.g.
    "duplicate_id", "broken_reference") so tests/tooling can filter by
    rule without parsing `message`. `registry`/`object_id` identify what
    the issue is about, when applicable; `details` carries whatever
    extra structured context that specific rule wants to attach (e.g.
    the id it collided with)."""

    severity: str
    rule: str
    message: str
    registry: Optional[str] = None
    object_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
        }
        if self.registry is not None:
            d["registry"] = self.registry
        if self.object_id is not None:
            d["object_id"] = self.object_id
        if self.details:
            d["details"] = self.details
        return d


def _error(rule: str, message: str, **kw: Any) -> ValidationIssue:
    return ValidationIssue(severity="error", rule=rule, message=message, **kw)


def _warning(rule: str, message: str, **kw: Any) -> ValidationIssue:
    return ValidationIssue(severity="warning", rule=rule, message=message, **kw)


def _info(rule: str, message: str, **kw: Any) -> ValidationIssue:
    """Third severity tier (Milestone 2): a non-critical, purely
    informational finding -- worth surfacing in the report but never
    something that should make status "fail" or that a human needs to
    act on before the compiler output can be trusted. See
    ValidationReport.status: only `errors` affects it, exactly as
    before this addition."""
    return ValidationIssue(severity="info", rule=rule, message=message, **kw)


@dataclass
class ValidationReport:
    """The full Phase B4 compiler artifact -- see module docstring's
    REPORT STRUCTURE section. Purely a data holder; all the actual
    checking happens in the module-level `_validate_*` functions below,
    which validate_compiler_state() calls and folds into one of these."""

    version: str
    generated_at: str
    issues: List[ValidationIssue] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    registry_summary: Dict[str, Any] = field(default_factory=dict)
    reference_summary: Dict[str, Any] = field(default_factory=dict)
    relationship_summary: Dict[str, Any] = field(default_factory=dict)
    integrity_summary: Dict[str, Any] = field(default_factory=dict)
    hierarchy_summary: Dict[str, Any] = field(default_factory=dict)
    topic_linking_summary: Dict[str, Any] = field(default_factory=dict)
    graph_summary: Dict[str, Any] = field(default_factory=dict)
    provenance_summary: Dict[str, Any] = field(default_factory=dict)
    structural_completeness_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "info"]

    @property
    def status(self) -> str:
        return "fail" if self.errors else "pass"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "status": self.status,
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
            "info": [i.to_dict() for i in self.infos],
            "statistics": self.statistics,
            "registry_summary": self.registry_summary,
            "reference_summary": self.reference_summary,
            "relationship_summary": self.relationship_summary,
            "integrity_summary": self.integrity_summary,
            "hierarchy_summary": self.hierarchy_summary,
            "topic_linking_summary": self.topic_linking_summary,
            "graph_summary": self.graph_summary,
            "provenance_summary": self.provenance_summary,
            "structural_completeness_summary": self.structural_completeness_summary,
        }


# --------------------------------------------------------------------------
# 1. Registry Integrity
# --------------------------------------------------------------------------

def _validate_registry_integrity(
    manager: RegistryManager,
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Unique ids, unique urns, duplicate lookup keys, duplicate aliases,
    registry consistency -- see task's own "Registry Integrity" list.
    Re-verifies, read-only, invariants CanonicalRegistry.insert() already
    enforces at write time (see compiler/registry.py's own DuplicateId/
    DuplicateUrn/DuplicateName errors) -- a defensive second look using
    only the registry's public API (.ids(), .values(), .get_by_id()),
    never its private indexes, so a registry populated by any means
    (insert(), deserialize(), a future bulk loader) is checked the same
    way."""
    issues: List[ValidationIssue] = []
    summary: Dict[str, Any] = {}

    for name in manager.names():
        registry = manager.get(name)
        ids = registry.ids()
        reg_summary: Dict[str, Any] = {"size": registry.size()}

        # -- unique ids (dict-backed, but confirm no accidental
        # id_of() collision slipped past insert() via a bulk path) --
        if len(ids) != len(set(ids)):
            issues.append(_error(
                "duplicate_id",
                f"{name}: registry.ids() contains duplicate id(s)",
                registry=name,
            ))
        reg_summary["duplicate_ids"] = len(ids) - len(set(ids))

        # -- registry consistency: get_by_id(id) round-trips to an item
        # whose own id field agrees with the key it was stored under --
        for id_ in ids:
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue
            if item.get("id") != id_:
                issues.append(_error(
                    "registry_consistency",
                    f"{name}: item stored under id {id_!r} reports its "
                    f"own id as {item.get('id')!r}",
                    registry=name, object_id=id_,
                ))

        # -- unique urns --
        urn_owner: Dict[str, str] = {}
        dup_urns = 0
        for id_ in ids:
            item = registry.get_by_id(id_)
            urn = item.get("urn") if isinstance(item, dict) else None
            if not urn:
                continue
            if urn in urn_owner and urn_owner[urn] != id_:
                dup_urns += 1
                issues.append(_error(
                    "duplicate_urn",
                    f"{name}: urn {urn!r} shared by {urn_owner[urn]!r} "
                    f"and {id_!r}",
                    registry=name, object_id=id_,
                    details={"urn": urn, "other_id": urn_owner[urn]},
                ))
            else:
                urn_owner[urn] = id_
        reg_summary["duplicate_urns"] = dup_urns

        # -- duplicate lookup keys / duplicate aliases: only meaningful
        # for the "concepts" registry (see module docstring's WHAT
        # "VALID" MEANS HERE section and compiler/registries.py's own
        # documented reasoning that duplicate titles/lookup keys are
        # LEGITIMATE and expected across the other eleven registries --
        # e.g. the same definition term recurring on two pages). Raising
        # this for every registry would flood the report with expected,
        # harmless duplication; concepts are the one registry where a
        # collision indicates the Single Owner Principle (Phase A) may
        # have been bypassed.
        if name == "concepts":
            key_owner: Dict[str, str] = {}
            dup_keys = 0
            for id_ in ids:
                item = registry.get_by_id(id_)
                key = item.get("canonical_lookup_key") if isinstance(item, dict) else None
                if not key:
                    continue
                if key in key_owner and key_owner[key] != id_:
                    dup_keys += 1
                    issues.append(_warning(
                        "duplicate_lookup_key",
                        f"concepts: canonical_lookup_key {key!r} shared "
                        f"by {key_owner[key]!r} and {id_!r} -- Phase B2's "
                        "concept lookup index already tolerates this by "
                        "dropping the ambiguous key (see compiler/"
                        "references.py), but it is worth a human's "
                        "attention.",
                        registry=name, object_id=id_,
                        details={"canonical_lookup_key": key, "other_id": key_owner[key]},
                    ))
                else:
                    key_owner[key] = id_
            reg_summary["duplicate_lookup_keys"] = dup_keys

            alias_owner: Dict[str, str] = {}
            dup_aliases = 0
            for id_ in ids:
                item = registry.get_by_id(id_)
                if not isinstance(item, dict):
                    continue
                for alias in (item.get("aliases") or []):
                    norm = alias.strip().lower() if isinstance(alias, str) else None
                    if not norm:
                        continue
                    if norm in alias_owner and alias_owner[norm] != id_:
                        dup_aliases += 1
                        issues.append(_warning(
                            "duplicate_alias",
                            f"concepts: alias {alias!r} shared by "
                            f"{alias_owner[norm]!r} and {id_!r}",
                            registry=name, object_id=id_,
                            details={"alias": alias, "other_id": alias_owner[norm]},
                        ))
                    else:
                        alias_owner[norm] = id_
            reg_summary["duplicate_aliases"] = dup_aliases

        summary[name] = reg_summary

    return issues, summary


# --------------------------------------------------------------------------
# 2. Canonical Object Integrity
# --------------------------------------------------------------------------

def _validate_canonical_object_integrity(
    manager: RegistryManager,
) -> List[ValidationIssue]:
    """Every canonical object should carry REQUIRED_CANONICAL_FIELDS plus
    a nested creation_metadata.compiler_version (see schemas/
    chapter_schema.py's CanonicalObjectBase / creation_metadata field).
    Reports missing/falsy fields; never fills one in (task's own "Do NOT
    modify them automatically")."""
    issues: List[ValidationIssue] = []
    for name in REGISTRY_NAMES:
        if not manager.has(name):
            continue
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                issues.append(_error(
                    "non_dict_item",
                    f"{name}: item {id_!r} is not a dict",
                    registry=name, object_id=id_,
                ))
                continue
            missing = [f for f in REQUIRED_CANONICAL_FIELDS if not item.get(f)]
            creation_metadata = item.get("creation_metadata")
            if not isinstance(creation_metadata, dict) or not creation_metadata.get("compiler_version"):
                missing.append("creation_metadata.compiler_version")
            if missing:
                issues.append(_error(
                    "missing_required_field",
                    f"{name}: item {id_!r} is missing required field(s): "
                    + ", ".join(missing),
                    registry=name, object_id=id_,
                    details={"missing_fields": missing},
                ))
    return issues


# --------------------------------------------------------------------------
# 3. Reference Integrity
# --------------------------------------------------------------------------

def _validate_reference_integrity(
    manager: RegistryManager,
    topics: Optional[Iterable[Dict[str, Any]]],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Verifies every reference field Phase B2 (compiler/references.py)
    and Phase A (topic_ids) put on a canonical object actually points at
    an object that exists -- concept_id, concept_ids, and (on Concept
    records only) the eleven _REVERSE_ID_FIELD reverse-aggregation
    fields. topic_ids can only be checked if `topics` is supplied (mirrors
    resolve_references()'s / resolve_relationships()'s own optional
    `topics` parameter) -- if it isn't, topic_ids references are counted
    as `not_checked`, never assumed broken OR assumed fine. Never repairs
    anything (task's own "Do NOT repair them")."""
    issues: List[ValidationIssue] = []
    checked = 0
    broken = 0
    not_checked = 0
    topic_ids_known: Optional[set] = (
        {t.get("id") for t in topics if isinstance(t, dict) and t.get("id")}
        if topics is not None else None
    )

    def _check(name: str, id_: str, field_name: str, target_registry: str, target_id: Any) -> None:
        nonlocal checked, broken
        if not target_id:
            return
        checked += 1
        if not manager.has(target_registry) or not manager.get(target_registry).contains(target_id):
            broken += 1
            issues.append(_error(
                "broken_reference",
                f"{name}: item {id_!r} field {field_name!r} references "
                f"{target_id!r}, which does not exist in {target_registry!r}",
                registry=name, object_id=id_,
                details={"field": field_name, "target_registry": target_registry, "target_id": target_id},
            ))

    for name in REGISTRY_NAMES:
        if not manager.has(name):
            continue
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue

            # concept_id (singular) -- definitions/glossary only, per B2.
            concept_id = item.get("concept_id")
            if concept_id:
                _check(name, id_, "concept_id", "concepts", concept_id)

            # concept_ids (plural) -- present (possibly empty) on every
            # non-concept registry per B2.
            for cid in (item.get("concept_ids") or []):
                _check(name, id_, "concept_ids", "concepts", cid)

            # topic_ids -- present on every canonical object per Phase A.
            for tid in (item.get("topic_ids") or []):
                if topic_ids_known is None:
                    not_checked += 1
                    continue
                checked += 1
                if tid not in topic_ids_known:
                    broken += 1
                    issues.append(_error(
                        "broken_reference",
                        f"{name}: item {id_!r} field 'topic_ids' "
                        f"references {tid!r}, which is not in the "
                        "supplied topics list",
                        registry=name, object_id=id_,
                        details={"field": "topic_ids", "target_id": tid},
                    ))

            # the eleven reverse-aggregation fields -- concepts only.
            if name == "concepts":
                for target_registry, field_name in _REVERSE_ID_FIELD.items():
                    for target_id in (item.get(field_name) or []):
                        _check(name, id_, field_name, target_registry, target_id)

    summary = {
        "checked": checked,
        "broken": broken,
        "not_checked": not_checked,
        "fields_covered": list(REFERENCE_FIELDS),
    }
    return issues, summary


# --------------------------------------------------------------------------
# 4. Relationship Integrity
# --------------------------------------------------------------------------

def _validate_relationship_integrity(
    manager: RegistryManager,
    topics: Optional[Iterable[Dict[str, Any]]],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """relationship ids unique, source exists, target exists, type valid,
    duplicate relationships absent, orphan relationships absent -- see
    task's own "Relationship Integrity" list. Never regenerates or
    repairs a relationship (task's own "Do NOT regenerate relationships.
    Only validate them.")."""
    issues: List[ValidationIssue] = []
    by_type: Dict[str, int] = {t: 0 for t in RELATIONSHIP_TYPES}
    broken_source = 0
    broken_target = 0
    invalid_type = 0
    duplicate_triples = 0
    orphans = 0
    topic_ids_known: Optional[set] = (
        {t.get("id") for t in topics if isinstance(t, dict) and t.get("id")}
        if topics is not None else None
    )

    if not manager.has(RELATIONSHIP_REGISTRY_NAME):
        # Absence itself is reported by _validate_compiler_state_integrity
        # (task's own "relationship registry exists" check belongs to
        # Compiler State Integrity, not here) -- this function simply has
        # nothing to validate.
        return issues, {
            "total": 0, "by_type": by_type, "broken_source": 0,
            "broken_target": 0, "invalid_type": 0,
            "duplicate_triples": 0, "orphans": 0,
        }

    registry = manager.get(RELATIONSHIP_REGISTRY_NAME)
    ids = registry.ids()

    if len(ids) != len(set(ids)):
        issues.append(_error(
            "duplicate_id",
            f"{RELATIONSHIP_REGISTRY_NAME}: registry.ids() contains "
            "duplicate id(s)",
            registry=RELATIONSHIP_REGISTRY_NAME,
        ))

    triple_owner: Dict[Tuple[str, str, str, str, str], str] = {}

    def _endpoint_exists(endpoint_type: Optional[str], endpoint_id: Optional[str]) -> Optional[bool]:
        """True/False if checkable, None if not (topic endpoint with no
        `topics` supplied, or an unrecognized endpoint type)."""
        if not endpoint_type or not endpoint_id:
            return False
        if endpoint_type == "topic":
            if topic_ids_known is None:
                return None
            return endpoint_id in topic_ids_known
        target_registry = _RELATIONSHIP_ENDPOINT_REGISTRY.get(endpoint_type)
        if target_registry is None:
            return None
        return manager.has(target_registry) and manager.get(target_registry).contains(endpoint_id)

    for rel_id in ids:
        rel = registry.get_by_id(rel_id)
        if not isinstance(rel, dict):
            continue

        rel_type = rel.get("type")
        source_type = rel.get("source_type")
        source_id = rel.get("source_id")
        target_type = rel.get("target_type")
        target_id = rel.get("target_id")

        if rel_type in by_type:
            by_type[rel_type] += 1
        else:
            invalid_type += 1
            issues.append(_error(
                "invalid_relationship_type",
                f"{RELATIONSHIP_REGISTRY_NAME}: relationship {rel_id!r} "
                f"has unrecognized type {rel_type!r}",
                registry=RELATIONSHIP_REGISTRY_NAME, object_id=rel_id,
                details={"type": rel_type},
            ))

        source_ok = _endpoint_exists(source_type, source_id)
        if source_ok is False:
            broken_source += 1
            issues.append(_error(
                "broken_relationship_source",
                f"{RELATIONSHIP_REGISTRY_NAME}: relationship {rel_id!r} "
                f"source {source_type}:{source_id!r} does not exist",
                registry=RELATIONSHIP_REGISTRY_NAME, object_id=rel_id,
                details={"source_type": source_type, "source_id": source_id},
            ))

        target_ok = _endpoint_exists(target_type, target_id)
        if target_ok is False:
            broken_target += 1
            issues.append(_error(
                "broken_relationship_target",
                f"{RELATIONSHIP_REGISTRY_NAME}: relationship {rel_id!r} "
                f"target {target_type}:{target_id!r} does not exist",
                registry=RELATIONSHIP_REGISTRY_NAME, object_id=rel_id,
                details={"target_type": target_type, "target_id": target_id},
            ))

        if source_ok is False and target_ok is False:
            orphans += 1

        triple = (rel_type, source_type, source_id, target_type, target_id)
        if triple in triple_owner and triple_owner[triple] != rel_id:
            duplicate_triples += 1
            issues.append(_error(
                "duplicate_relationship",
                f"{RELATIONSHIP_REGISTRY_NAME}: relationships "
                f"{triple_owner[triple]!r} and {rel_id!r} both represent "
                f"the same (type, source, target) triple",
                registry=RELATIONSHIP_REGISTRY_NAME, object_id=rel_id,
                details={"other_id": triple_owner[triple]},
            ))
        else:
            triple_owner[triple] = rel_id

    summary = {
        "total": len(ids),
        "by_type": by_type,
        "broken_source": broken_source,
        "broken_target": broken_target,
        "invalid_type": invalid_type,
        "duplicate_triples": duplicate_triples,
        "orphans": orphans,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 5. Compiler State Integrity
# --------------------------------------------------------------------------

def _validate_compiler_state_integrity(
    manager: RegistryManager,
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """all required registries exist, relationship registry exists,
    registry ownership is correct -- see task's own "Compiler State
    Integrity" list. "compiler state is internally consistent" is
    interpreted, per the task's own PIPELINE note that this pass runs
    BEFORE compiler_state.set_current_registry_manager(), as validating
    `manager` itself (the object about to become "current"), not
    compiler.state's module-level slot (which is not populated yet at
    the point this pass runs -- see compiler/validation.py's own module
    docstring PIPELINE INTEGRATION section)."""
    issues: List[ValidationIssue] = []
    missing_registries = [n for n in REGISTRY_NAMES if not manager.has(n)]
    for n in missing_registries:
        issues.append(_error(
            "missing_registry",
            f"required registry {n!r} is missing from the RegistryManager",
            registry=n,
        ))

    relationship_registry_present = manager.has(RELATIONSHIP_REGISTRY_NAME)
    if not relationship_registry_present:
        issues.append(_error(
            "missing_relationship_registry",
            f"{RELATIONSHIP_REGISTRY_NAME!r} registry is missing from "
            "the RegistryManager -- Phase B3 (resolve_relationships) may "
            "not have run yet",
            registry=RELATIONSHIP_REGISTRY_NAME,
        ))

    ownership_mismatches = []
    for name in manager.names():
        registry = manager.get(name)
        if registry.name != name:
            ownership_mismatches.append(name)
            issues.append(_error(
                "registry_ownership_mismatch",
                f"registry stored under key {name!r} reports its own "
                f"name as {registry.name!r}",
                registry=name,
            ))

    summary = {
        "required_registries_present": len(missing_registries) == 0,
        "missing_registries": missing_registries,
        "relationship_registry_present": relationship_registry_present,
        "registry_ownership_ok": len(ownership_mismatches) == 0,
        "registries_present": list(manager.names()),
    }
    return issues, summary


# --------------------------------------------------------------------------
# 6. Determinism Validation
# --------------------------------------------------------------------------

def _check_id_determinism(
    manager: RegistryManager,
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """registry ordering deterministic, relationship ordering
    deterministic, ids deterministic, urns deterministic -- see task's
    own "Determinism Validation" list.

    "Ordering deterministic" is verified structurally: CanonicalRegistry
    stores items in a plain dict (compiler/registry.py), and Python
    dicts have guaranteed insertion-order iteration since 3.7 -- so
    registry.ids()/.values() are deterministic BY LANGUAGE GUARANTEE, not
    by any property this pass could break or fix. What this pass DOES
    meaningfully check is that nothing violated the one invariant that
    guarantee depends on: no id appearing twice (already checked in
    _validate_registry_integrity/_validate_relationship_integrity; not
    repeated here).

    "IDs/urns deterministic" is checked two ways: (a) a structural shape
    check against the slugify-then-sha1 pattern every id/urn generator
    in this codebase (modules.pdf_parser.make_id/make_urn,
    compiler.relationships._relationship_id) produces -- a WARNING, not
    an error, if an id/urn doesn't match, since a hand-built test fixture
    or a future generator using a different-but-still-deterministic
    scheme is legitimate, just worth a human's attention; and (b), for
    every relationship specifically, RECOMPUTING _relationship_id() from
    that relationship's own stored (type, source_id, target_id) and
    comparing it to the stored id -- the strongest available proof that
    a given relationship id really is a pure function of its own content
    and not, say, a random UUID -- also a WARNING (not an error) since a
    relationship_resolution.version older than RELATIONSHIP_RESOLUTION_
    VERSION could legitimately have used a since-changed algorithm.
    """
    issues: List[ValidationIssue] = []
    non_deterministic_ids = 0
    non_deterministic_urns = 0

    for name in manager.names():
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue
            obj_id = item.get("id")
            if obj_id and not _DETERMINISTIC_ID_PATTERN.match(obj_id):
                non_deterministic_ids += 1
                issues.append(_warning(
                    "id_shape_unexpected",
                    f"{name}: id {obj_id!r} does not match the "
                    "deterministic slugify+sha1 shape every id generator "
                    "in this codebase produces",
                    registry=name, object_id=obj_id,
                ))
            urn = item.get("urn")
            if urn and not _DETERMINISTIC_URN_PATTERN.match(urn):
                non_deterministic_urns += 1
                issues.append(_warning(
                    "urn_shape_unexpected",
                    f"{name}: urn {urn!r} does not match the expected "
                    "'urn:<namespace>:...' shape",
                    registry=name, object_id=obj_id,
                ))

    recomputation_mismatches = 0
    if manager.has(RELATIONSHIP_REGISTRY_NAME):
        registry = manager.get(RELATIONSHIP_REGISTRY_NAME)
        for rel_id in registry.ids():
            rel = registry.get_by_id(rel_id)
            if not isinstance(rel, dict):
                continue
            expected_id = _relationship_id(
                "relationship", rel.get("type") or "",
                rel.get("source_id") or "", rel.get("target_id") or "",
            )
            if expected_id != rel_id:
                recomputation_mismatches += 1
                issues.append(_warning(
                    "relationship_id_not_reproducible",
                    f"{RELATIONSHIP_REGISTRY_NAME}: relationship "
                    f"{rel_id!r} does not match recomputing "
                    "_relationship_id() from its own stored "
                    "type/source_id/target_id",
                    registry=RELATIONSHIP_REGISTRY_NAME, object_id=rel_id,
                    details={"expected_id": expected_id},
                ))

    summary = {
        "id_shape_violations": non_deterministic_ids,
        "urn_shape_violations": non_deterministic_urns,
        "relationship_id_recomputation_mismatches": recomputation_mismatches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 7. Hierarchy Integrity (Milestone 2)
# --------------------------------------------------------------------------

def _validate_hierarchy_integrity(
    topics: Optional[Iterable[Dict[str, Any]]],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Validates the topic hierarchy itself -- schemas/chapter_schema.py's
    TopicNode.parent / TopicNode.children, a flat list of nodes forming a
    parent-pointer tree, not a nested structure. Read-only, exactly like
    every other check in this module: no `topics` entry is ever mutated.

    Only meaningful if `topics` is supplied (mirrors every other
    `topics`-optional check in this module) -- if it isn't, this whole
    category is skipped and `hierarchy_summary["checked"]` is False, never
    silently treated as "valid".

    Checks:
      - duplicate topic ids (error -- breaks every other check below,
        which all key off id uniqueness)
      - every `parent` references an existing topic id, or is None/empty
        (root) (error: broken_hierarchy_parent)
      - every id in `children` references an existing topic id (error:
        broken_hierarchy_child)
      - parent/children mutual consistency: if A.parent == B, B.children
        should contain A, and vice versa (warning: hierarchy_link_
        mismatch -- worth a human's attention, but Phase A already
        derives one direction from PDF heading structure and the other
        may simply not have been back-filled for every node)
      - no cycles in the parent chain (error: hierarchy_cycle -- a cycle
        would make any parent-walk in a later phase infinite-loop)
    """
    issues: List[ValidationIssue] = []
    if topics is None:
        return issues, {"checked": False}

    topic_list = [t for t in topics if isinstance(t, dict) and t.get("id")]
    by_id: Dict[str, Dict[str, Any]] = {}
    duplicate_ids = 0
    for t in topic_list:
        tid = t["id"]
        if tid in by_id:
            duplicate_ids += 1
            issues.append(_error(
                "duplicate_id",
                f"topics: hierarchy contains duplicate topic id {tid!r}",
                registry="topics", object_id=tid,
            ))
        else:
            by_id[tid] = t

    broken_parents = 0
    broken_children = 0
    link_mismatches = 0
    for tid, t in by_id.items():
        parent = t.get("parent")
        if parent:
            if parent not in by_id:
                broken_parents += 1
                issues.append(_error(
                    "broken_hierarchy_parent",
                    f"topics: {tid!r} has parent {parent!r}, which does "
                    "not exist",
                    registry="topics", object_id=tid,
                    details={"parent": parent},
                ))
            elif tid not in (by_id[parent].get("children") or []):
                link_mismatches += 1
                issues.append(_warning(
                    "hierarchy_link_mismatch",
                    f"topics: {tid!r} declares parent {parent!r}, but "
                    f"{parent!r}.children does not list {tid!r} back",
                    registry="topics", object_id=tid,
                    details={"parent": parent},
                ))
        for child in (t.get("children") or []):
            if child not in by_id:
                broken_children += 1
                issues.append(_error(
                    "broken_hierarchy_child",
                    f"topics: {tid!r} lists child {child!r}, which does "
                    "not exist",
                    registry="topics", object_id=tid,
                    details={"child": child},
                ))
            elif by_id[child].get("parent") != tid:
                link_mismatches += 1
                issues.append(_warning(
                    "hierarchy_link_mismatch",
                    f"topics: {tid!r} lists child {child!r}, but "
                    f"{child!r}.parent is {by_id[child].get('parent')!r}, "
                    f"not {tid!r}",
                    registry="topics", object_id=tid,
                    details={"child": child},
                ))

    cycles = 0
    cyclic_ids: set = set()
    for start in by_id:
        if start in cyclic_ids:
            continue
        seen: List[str] = []
        current: Optional[str] = start
        visited_this_walk: set = set()
        while current is not None:
            if current in visited_this_walk:
                cycles += 1
                cyclic_ids.update(seen)
                issues.append(_error(
                    "hierarchy_cycle",
                    "topics: cycle detected in parent chain starting at "
                    f"{start!r} (revisits {current!r})",
                    registry="topics", object_id=start,
                    details={"chain": seen},
                ))
                break
            visited_this_walk.add(current)
            seen.append(current)
            node = by_id.get(current)
            current = node.get("parent") if node else None

    summary = {
        "checked": True,
        "total_topics": len(topic_list),
        "duplicate_ids": duplicate_ids,
        "broken_parents": broken_parents,
        "broken_children": broken_children,
        "link_mismatches": link_mismatches,
        "cycles": cycles,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 8. Topic Linking Integrity (Milestone 2 -- builds on Milestone 1's
#    modules/topic_linker.py universal object linking)
# --------------------------------------------------------------------------

def _validate_topic_linking_integrity(
    manager: RegistryManager,
    topics: Optional[Iterable[Dict[str, Any]]],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Verifies that Milestone 1's forward (`topic_ids` on the canonical
    object) and reverse (the matching list field on TopicNode, e.g.
    `TopicNode.figures`) links exactly agree with each other, for every
    object type `modules/topic_linker.TOPIC_REVERSE_FIELDS` gives a
    reverse slot to. This is the one check neither Phase B2
    (compiler/references.py, forward-only) nor the existing Reference
    Integrity check above (also forward-only) already performs -- see
    module docstring addendum.

    Only meaningful if `topics` is supplied. Never repairs a mismatch;
    only reports it."""
    issues: List[ValidationIssue] = []
    if topics is None:
        return issues, {"checked": False}

    by_id: Dict[str, Dict[str, Any]] = {
        t["id"]: t for t in topics if isinstance(t, dict) and t.get("id")
    }

    forward_missing_from_reverse = 0
    reverse_missing_from_forward = 0
    reverse_to_nonexistent_object = 0
    duplicate_reverse_entries = 0
    checked_pairs = 0

    for registry_name in _TOPIC_LINKED_REGISTRIES:
        if not manager.has(registry_name):
            continue
        registry = manager.get(registry_name)

        # forward -> reverse: every object claiming a topic_id should be
        # listed in that topic's matching reverse field.
        for obj_id in registry.ids():
            item = registry.get_by_id(obj_id)
            if not isinstance(item, dict):
                continue
            for tid in (item.get("topic_ids") or []):
                topic = by_id.get(tid)
                if topic is None:
                    continue  # reported separately by Reference Integrity
                checked_pairs += 1
                reverse_list = topic.get(registry_name) or []
                if obj_id not in reverse_list:
                    forward_missing_from_reverse += 1
                    issues.append(_error(
                        "reverse_reference_missing",
                        f"{registry_name}: {obj_id!r} declares topic_ids "
                        f"including {tid!r}, but topic {tid!r}.{registry_name} "
                        f"does not list {obj_id!r} back",
                        registry=registry_name, object_id=obj_id,
                        details={"topic_id": tid, "reverse_field": registry_name},
                    ))

        # reverse -> forward: every id in a topic's reverse list should
        # exist in the registry and claim that topic back.
        for tid, topic in by_id.items():
            reverse_list = topic.get(registry_name) or []
            seen_this_list: set = set()
            for obj_id in reverse_list:
                if obj_id in seen_this_list:
                    duplicate_reverse_entries += 1
                    issues.append(_warning(
                        "duplicate_reverse_reference",
                        f"topics: {tid!r}.{registry_name} lists {obj_id!r} "
                        "more than once",
                        registry="topics", object_id=tid,
                        details={"reverse_field": registry_name, "target_id": obj_id},
                    ))
                    continue
                seen_this_list.add(obj_id)
                item = registry.get_by_id(obj_id) if registry.contains(obj_id) else None
                if item is None:
                    reverse_to_nonexistent_object += 1
                    issues.append(_error(
                        "broken_reference",
                        f"topics: {tid!r}.{registry_name} references "
                        f"{obj_id!r}, which does not exist in "
                        f"{registry_name!r}",
                        registry="topics", object_id=tid,
                        details={"reverse_field": registry_name, "target_id": obj_id},
                    ))
                    continue
                if tid not in (item.get("topic_ids") or []):
                    reverse_missing_from_forward += 1
                    issues.append(_error(
                        "forward_reference_missing",
                        f"topics: {tid!r}.{registry_name} lists {obj_id!r}, "
                        f"but {registry_name}:{obj_id!r}.topic_ids does not "
                        f"list {tid!r} back",
                        registry=registry_name, object_id=obj_id,
                        details={"topic_id": tid, "reverse_field": registry_name},
                    ))

    summary = {
        "checked": True,
        "registries_covered": list(_TOPIC_LINKED_REGISTRIES),
        "checked_pairs": checked_pairs,
        "forward_missing_from_reverse": forward_missing_from_reverse,
        "reverse_missing_from_forward": reverse_missing_from_forward,
        "reverse_to_nonexistent_object": reverse_to_nonexistent_object,
        "duplicate_reverse_entries": duplicate_reverse_entries,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 9. Graph Integrity (Milestone 2)
# --------------------------------------------------------------------------

def _validate_graph_integrity(
    manager: RegistryManager,
    topics: Optional[Iterable[Dict[str, Any]]],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Treats `topic_ids`/relationship endpoints as directed edges of one
    object graph and looks for two things neither Reference Integrity nor
    Relationship Integrity above already reports: duplicate edges
    (the same target id repeated inside one object's own reference list)
    and orphan nodes (a canonical object connected to nothing -- no
    topic_ids AND not a source/target of any relationship). Orphan nodes
    are reported at `info` severity: per modules/topic_linker.py's own
    documented design, an object that genuinely has no deterministic page
    match is SUPPOSED to end up unlinked rather than guessed at, so this
    is worth surfacing, not treated as broken."""
    issues: List[ValidationIssue] = []
    duplicate_edges = 0
    orphan_nodes = 0

    connected_ids: set = set()
    if manager.has(RELATIONSHIP_REGISTRY_NAME):
        rel_registry = manager.get(RELATIONSHIP_REGISTRY_NAME)
        for rel_id in rel_registry.ids():
            rel = rel_registry.get_by_id(rel_id)
            if not isinstance(rel, dict):
                continue
            if rel.get("source_id"):
                connected_ids.add(rel.get("source_id"))
            if rel.get("target_id"):
                connected_ids.add(rel.get("target_id"))

    for name in REGISTRY_NAMES:
        if not manager.has(name):
            continue
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue

            for field_name in ("topic_ids", "concept_ids"):
                values = item.get(field_name) or []
                if len(values) != len(set(values)):
                    duplicate_edges += 1
                    issues.append(_warning(
                        "duplicate_reference",
                        f"{name}: item {id_!r} field {field_name!r} "
                        "contains duplicate target id(s)",
                        registry=name, object_id=id_,
                        details={"field": field_name},
                    ))

            topic_ids = item.get("topic_ids") or []
            if not topic_ids and id_ not in connected_ids and name != "topics":
                orphan_nodes += 1
                issues.append(_info(
                    "orphan_object",
                    f"{name}: item {id_!r} has no topic_ids and is not "
                    "referenced by any relationship -- structurally "
                    "valid, but unconnected to the rest of the graph",
                    registry=name, object_id=id_,
                ))

    if topics is not None:
        for t in topics:
            if not isinstance(t, dict) or not t.get("id"):
                continue
            has_reverse_content = any(
                t.get(field_name) for field_name in set(TOPIC_REVERSE_FIELDS.values()) - {None}
            )
            if not t.get("parent") and not t.get("children") and not has_reverse_content:
                orphan_nodes += 1
                issues.append(_info(
                    "orphan_object",
                    f"topics: {t['id']!r} has no parent, no children, and "
                    "no reverse-linked content",
                    registry="topics", object_id=t["id"],
                ))

    summary = {
        "duplicate_edges": duplicate_edges,
        "orphan_nodes": orphan_nodes,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 10. Provenance Integrity (Milestone 2)
# --------------------------------------------------------------------------

def _validate_provenance_integrity(
    manager: RegistryManager,
    page_count: Optional[int],
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Every canonical object must carry a `provenance` dict (error if
    entirely missing -- Canonical Object Integrity above only checks that
    the *key* is present/truthy, not that it usefully identifies a page).
    `provenance.source_page` missing is a warning, not an error: several
    legitimate object types (e.g. a chapter-level Concept aggregated
    across pages) do not have one deterministic source page -- see
    schemas/chapter_schema.py's own Provenance docstring ("not every
    object type has a meaningful value for every field"). If `page_count`
    is supplied (0-indexed page range, matching pdf_parser's own page
    numbering -- see pipeline.py's `structure.num_pages`), a source_page
    outside `[0, page_count - 1]` is an error: that page cannot exist in
    this chapter's own PDF, so the provenance record is simply wrong, not
    just incomplete."""
    issues: List[ValidationIssue] = []
    missing_provenance = 0
    missing_source_page = 0
    invalid_source_page = 0
    checked = 0

    for name in REGISTRY_NAMES:
        if not manager.has(name):
            continue
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue
            checked += 1
            provenance = item.get("provenance")
            if not isinstance(provenance, dict):
                missing_provenance += 1
                issues.append(_error(
                    "missing_provenance",
                    f"{name}: item {id_!r} has no provenance record",
                    registry=name, object_id=id_,
                ))
                continue

            source_page = provenance.get("source_page")
            if source_page is None:
                missing_source_page += 1
                issues.append(_warning(
                    "provenance_missing_page",
                    f"{name}: item {id_!r}.provenance.source_page is not set",
                    registry=name, object_id=id_,
                ))
            elif page_count is not None and (
                not isinstance(source_page, int)
                or isinstance(source_page, bool)
                or not (0 <= source_page < page_count)
            ):
                invalid_source_page += 1
                issues.append(_error(
                    "provenance_invalid_page",
                    f"{name}: item {id_!r}.provenance.source_page="
                    f"{source_page!r} falls outside this chapter's page "
                    f"range [0, {page_count - 1}]",
                    registry=name, object_id=id_,
                    details={"source_page": source_page, "page_count": page_count},
                ))

    summary = {
        "checked": checked,
        "missing_provenance": missing_provenance,
        "missing_source_page": missing_source_page,
        "invalid_source_page": invalid_source_page,
        "page_count_supplied": page_count is not None,
    }
    return issues, summary


# --------------------------------------------------------------------------
# 11. Structural Completeness (Milestone 2)
# --------------------------------------------------------------------------

def _validate_structural_completeness(
    manager: RegistryManager,
) -> Tuple[List[ValidationIssue], Dict[str, Any]]:
    """Catches compiler output that is present but incomplete, beyond
    what Canonical Object Integrity (REQUIRED_CANONICAL_FIELDS) already
    covers: a missing `topic_ids`/`concept_ids` *key* entirely (as
    opposed to a present-but-empty list, which Milestone 1 documents as
    a legitimate "nothing matched" outcome, not an error), and an item
    stored under a registry whose own `object_type` says it belongs
    somewhere else (inconsistent object ownership)."""
    issues: List[ValidationIssue] = []
    missing_topic_ids_field = 0
    missing_concept_ids_field = 0
    ownership_mismatches = 0

    for name in REGISTRY_NAMES:
        if not manager.has(name):
            continue
        expected_type = OBJECT_TYPE_BY_REGISTRY.get(name)
        registry = manager.get(name)
        for id_ in registry.ids():
            item = registry.get_by_id(id_)
            if not isinstance(item, dict):
                continue
            if "topic_ids" not in item:
                missing_topic_ids_field += 1
                issues.append(_error(
                    "missing_topic_ids_field",
                    f"{name}: item {id_!r} has no 'topic_ids' key at all",
                    registry=name, object_id=id_,
                ))
            if "concept_ids" not in item:
                missing_concept_ids_field += 1
                issues.append(_error(
                    "missing_concept_ids_field",
                    f"{name}: item {id_!r} has no 'concept_ids' key at all",
                    registry=name, object_id=id_,
                ))
            actual_type = item.get("object_type")
            if expected_type and actual_type and actual_type != expected_type:
                ownership_mismatches += 1
                issues.append(_error(
                    "inconsistent_object_ownership",
                    f"{name}: item {id_!r} has object_type {actual_type!r}, "
                    f"expected {expected_type!r} for this registry",
                    registry=name, object_id=id_,
                    details={"expected_type": expected_type, "actual_type": actual_type},
                ))

    summary = {
        "missing_topic_ids_field": missing_topic_ids_field,
        "missing_concept_ids_field": missing_concept_ids_field,
        "ownership_mismatches": ownership_mismatches,
    }
    return issues, summary


# --------------------------------------------------------------------------
# Top-level entry point -- pipeline.py's single integration point
# --------------------------------------------------------------------------

def validate_compiler_state(
    manager: RegistryManager,
    *,
    topics: Optional[Iterable[Dict[str, Any]]] = None,
    page_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Phase B4's single pipeline.py integration point (mirrors
    compiler.references.resolve_references()'s and compiler.relationships
    .resolve_relationships()'s own shape). Must run AFTER
    resolve_relationships() and BEFORE
    compiler_state.set_current_registry_manager() -- see module
    docstring's PIPELINE INTEGRATION section and pipeline.py's own
    comment at the call site.

    Read-only over `manager` and `topics`: no registry is inserted into,
    updated, or removed from; no item dict anywhere is mutated; `topics`
    is only ever read. Runs all eleven validation categories the task
    spec lists (registry integrity, canonical object integrity,
    reference integrity, relationship integrity, compiler state
    integrity, determinism validation, hierarchy integrity, topic
    linking integrity, graph integrity, provenance integrity, structural
    completeness) and folds their issues/summaries into one
    ValidationReport, returned here as a plain dict (report.to_dict())
    for the same "plain, storable dict" reasons resolve_relationships()
    already documents for its own return value, and so it can be handed
    directly to compiler_state.set_current_validation_report() (task's
    own "the validation report should become part of the compiler
    state").

    Milestone 2 wiring fix: `_validate_hierarchy_integrity`,
    `_validate_topic_linking_integrity`, `_validate_graph_integrity`,
    `_validate_provenance_integrity`, and `_validate_structural_
    completeness` were already fully implemented below (sections 7-11)
    -- and `ValidationReport` already had dedicated summary fields
    waiting for their output -- but none of the five were ever actually
    called from this entry point, so none of them ever ran against a
    real chapter. They are wired in here, in the same section-number
    order they appear in below, so nothing that was already implemented
    keeps silently not running. `page_count`, new here, is threaded
    through only to `_validate_provenance_integrity` (the one check that
    needs it, to catch a `source_page` outside this chapter's own PDF
    page range); every other new call already only needs `manager`/
    `topics`, which this function already received.
    """
    report = ValidationReport(
        version=VALIDATION_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    registry_issues, registry_summary = _validate_registry_integrity(manager)
    report.issues.extend(registry_issues)
    report.registry_summary = registry_summary

    report.issues.extend(_validate_canonical_object_integrity(manager))

    reference_issues, reference_summary = _validate_reference_integrity(manager, topics)
    report.issues.extend(reference_issues)
    report.reference_summary = reference_summary

    relationship_issues, relationship_summary = _validate_relationship_integrity(manager, topics)
    report.issues.extend(relationship_issues)
    report.relationship_summary = relationship_summary

    state_issues, state_summary = _validate_compiler_state_integrity(manager)
    report.issues.extend(state_issues)

    determinism_issues, determinism_summary = _check_id_determinism(manager)
    report.issues.extend(determinism_issues)

    report.integrity_summary = {**state_summary, "determinism": determinism_summary}

    hierarchy_issues, hierarchy_summary = _validate_hierarchy_integrity(topics)
    report.issues.extend(hierarchy_issues)
    report.hierarchy_summary = hierarchy_summary

    topic_linking_issues, topic_linking_summary = _validate_topic_linking_integrity(manager, topics)
    report.issues.extend(topic_linking_issues)
    report.topic_linking_summary = topic_linking_summary

    graph_issues, graph_summary = _validate_graph_integrity(manager, topics)
    report.issues.extend(graph_issues)
    report.graph_summary = graph_summary

    provenance_issues, provenance_summary = _validate_provenance_integrity(manager, page_count)
    report.issues.extend(provenance_issues)
    report.provenance_summary = provenance_summary

    structural_issues, structural_summary = _validate_structural_completeness(manager)
    report.issues.extend(structural_issues)
    report.structural_completeness_summary = structural_summary

    report.statistics = {
        "registries_checked": len(manager.names()),
        "total_canonical_objects": sum(
            manager.get(n).size() for n in REGISTRY_NAMES if manager.has(n)
        ),
        "total_relationships": relationship_summary.get("total", 0),
        "total_errors": len(report.errors),
        "total_warnings": len(report.warnings),
    }

    return report.to_dict()