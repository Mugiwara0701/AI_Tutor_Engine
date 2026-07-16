"""
document_structure_tree/enums.py — Milestone 1: closed enumerations
required by the frozen schema.

SCOPE: every closed-set vocabulary defined by the frozen architecture/
schema is implemented here as a `str`-backed `Enum` (JSON-serializable
via `.value`, comparable directly against the equivalent string).

A NOTE ON WHAT IS -- AND ISN'T -- HERE, RELATIVE TO THE ROADMAP: the
implementation roadmap's M0/M1 text lists "EntryType, ObjectType,
ValidationStatus, HeadingDetectionMethod, InvariantId" together as
illustrative examples of enums to implement. The frozen schema itself
(`DST_Schema_Design_v1.1.md` §2.1) draws a sharper line: `EntryType`
is explicitly "Closed set — this is a discriminator, not extensible";
`ObjectType` is explicitly "Open string set owned by the canonical
registries, not enumerated here". Those are different contracts, and
this module follows the schema's own classification rather than the
roadmap's grouping: `ObjectType` is implemented in primitives.py as an
opaque, non-enumerated string type, not here. See that module's
docstring for the fuller rationale. `HeadingDetectionMethod` sits in
between -- schema §2.1 calls it "a compiler-internal vocabulary" with
an explicit "..." after its listed examples, and schema §2.4 confirms
no Phase 2 contract depends on its values. It is included here as an
`Enum` covering the values the schema itself lists, on the
understanding (documented on the class itself) that -- unlike the
other three enums below -- extending it later is a compiler-internal
change, not a `schema_version`-relevant one.

Nothing in this module is a "DST construction" concern: these are pure
vocabulary, exactly like primitives.py, with no dependency on tree
assembly or the validation engine.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from .exceptions import DSTSerializationError

__all__ = [
    "EntryType",
    "ValidationStatus",
    "HeadingDetectionMethod",
    "InvariantId",
]


class _JsonStrEnum(str, Enum):
    """Shared base for every enum in this module: serializes as its
    own lowercase-or-as-declared string value (schema §5.1: "Enum
    values are serialized as lowercase strings"), and decodes back via
    a validating `from_json` that raises the same
    `DSTSerializationError` every other composite type in this package
    raises for an unrecognized/malformed JSON value, rather than a
    raw `ValueError` from the stdlib `Enum` constructor."""

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, data: Any) -> "_JsonStrEnum":
        if not isinstance(data, str):
            raise DSTSerializationError(
                f"{cls.__name__}.from_json expects a string, got {type(data).__name__}."
            )
        try:
            return cls(data)
        except ValueError as exc:
            valid = ", ".join(repr(member.value) for member in cls)
            raise DSTSerializationError(
                f"{data!r} is not a valid {cls.__name__} value; expected one of: {valid}."
            ) from exc


class EntryType(_JsonStrEnum):
    """`heading` | `content` (architecture §11, schema §2.1). Closed
    set — this is a discriminator, not extensible; a third value would
    be a `MAJOR` schema-version-bumping change (schema §5.7, §7)."""

    HEADING = "heading"
    CONTENT = "content"


class ValidationStatus(_JsonStrEnum):
    """`pass` | `fail` (schema §2.5) — the overall and per-invariant
    result of running the §15 invariant suite. Closed by definition:
    there is no third outcome anywhere in the frozen architecture."""

    PASS = "pass"
    FAIL = "fail"


class HeadingDetectionMethod(_JsonStrEnum):
    """Compiler-internal vocabulary describing how a heading was
    detected (architecture §9.2, schema §2.1: "String drawn from a
    compiler-internal vocabulary ... no Phase 2 contract depends on
    its values"). Unlike `EntryType`/`ValidationStatus`/`InvariantId`,
    this set is NOT closed by the frozen architecture itself -- the
    schema's own listing ends in "...", signaling further compiler-
    internal methods may exist. The members below are exactly the
    methods the schema document names; adding a new member later
    (a new detection technique) is a compiler-internal change and,
    per schema §2.4, never triggers a `schema_version` bump or
    invalidates any §15/§17 guarantee, unlike the other three enums
    in this module."""

    LAYOUT_ANALYSIS = "layout_analysis"
    TYPOGRAPHY = "typography"
    TOC_MATCHING = "toc_matching"
    VLM_INFERENCE = "vlm_inference"
    HEURISTIC_MERGING = "heuristic_merging"


class InvariantId(_JsonStrEnum):
    """`S1`-`S4`, `R1`-`R4`, `O1`-`O2`, `I1`-`I3`, `B1`-`B3` (schema
    §2.1: "Closed set defined by the frozen architecture's validation
    specification"). This is the complete, exhaustive set of sixteen
    invariants defined in architecture §15 at the time this schema was
    frozen; an additive change to that set is described by the schema
    itself (§2.5) as something that "should never require a
    corresponding schema-version bump" -- i.e. this enum may grow in a
    future, compatible revision without that being a breaking change,
    but no such addition is anticipated or invented here."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    O1 = "O1"
    O2 = "O2"
    I1 = "I1"
    I2 = "I2"
    I3 = "I3"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
