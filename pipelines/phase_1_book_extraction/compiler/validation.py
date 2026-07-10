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

PIPELINE INTEGRATION: validate_compiler_state(manager, *, topics=None) is
the one pipeline.py integration point, mirroring resolve_references()'s
and resolve_relationships()'s own shape exactly. It must run AFTER
compiler.relationships.resolve_relationships() (so the "relationships"
registry already exists and is fully populated to validate) and BEFORE
compiler_state.set_current_registry_manager() (so validation genuinely
inspects "the IR as it will be handed to later phases", not a stale
snapshot) -- see pipeline.py's own integration comment at the call site.
The returned report is handed to compiler_state.set_current_validation_
report() immediately after (a Phase B4 addition to compiler/state.py --
see that module's own docstring), making it "part of the compiler
state" per the task spec, WITHOUT writing it into ChapterJSON or onto
`manager` itself.

REPORT STRUCTURE: validate_compiler_state() returns a plain dict (see
ValidationReport.to_dict() below) with: `version`, `generated_at`,
`status` ("pass"/"fail"), `errors` (list), `warnings` (list),
`statistics`, `registry_summary`, `reference_summary`,
`relationship_summary`, `integrity_summary`. This dict is the compiler
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

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

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
            "statistics": self.statistics,
            "registry_summary": self.registry_summary,
            "reference_summary": self.reference_summary,
            "relationship_summary": self.relationship_summary,
            "integrity_summary": self.integrity_summary,
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
# Top-level entry point -- pipeline.py's single integration point
# --------------------------------------------------------------------------

def validate_compiler_state(
    manager: RegistryManager,
    *,
    topics: Optional[Iterable[Dict[str, Any]]] = None,
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
    is only ever read. Runs all six validation categories the task spec
    lists (registry integrity, canonical object integrity, reference
    integrity, relationship integrity, compiler state integrity,
    determinism validation) and folds their issues/summaries into one
    ValidationReport, returned here as a plain dict (report.to_dict())
    for the same "plain, storable dict" reasons resolve_relationships()
    already documents for its own return value, and so it can be handed
    directly to compiler_state.set_current_validation_report() (task's
    own "the validation report should become part of the compiler
    state").
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