"""
document_structure_tree/serialization.py — Milestone 1: generic
serialization infrastructure.

SCOPE: this module provides the reusable vocabulary every DST model --
today's primitives (primitives.py) and every later milestone's models
(HeadingNode, SequenceEntry, ArtifactMetadata, ...) -- builds its own
`to_json`/`from_json` methods out of:

- `OMIT`, a sentinel marking "optional and absent" so it can be told
  apart from a real, meaningful `None` (schema §5.3's distinction
  between field omission and explicit `null`).
- `json_object`, which builds a JSON-serializable dict from (key,
  value) pairs, dropping any pair marked `OMIT` while preserving an
  explicit `None` (needed for `parent_id`, the schema's one
  "Required, nullable" field -- not introduced until a later
  milestone, but this helper is written to support it correctly when
  it arrives).
- A small set of `require_*` validators shared by every primitive type
  in primitives.py, so "what counts as a valid non-empty identifier"
  etc. is defined exactly once.
- `round_trip`, the generic encode -> decode -> re-encode harness
  every primitive's tests are built on (roadmap M0 deliverable: "A
  round-trip test harness").

This module intentionally has no dependency on primitives.py (the
dependency runs the other way) and defines no DST-specific model of
its own -- it is pure, general-purpose scaffolding, matching the
milestone's "no DST construction logic in this milestone" scope.

Every type in this package that participates in JSON serialization is
expected to implement the informal `JsonSerializable` protocol below:
an instance method `to_json(self) -> Any` and a classmethod
`from_json(cls, data: Any) -> "Self"`. This is documented as a
`typing.Protocol` rather than an ABC so plain, frozen dataclasses (the
convention this package follows -- see primitives.py) can satisfy it
structurally, without an inheritance requirement.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, Protocol, Tuple, TypeVar, runtime_checkable

from .exceptions import DSTSerializationError, DSTValueError

__all__ = [
    "OMIT",
    "Omitted",
    "json_object",
    "JsonSerializable",
    "round_trip",
    "require_non_empty_str",
    "require_non_negative_int",
    "require_semver",
    "require_iso8601_utc",
    "require_sha256_hex",
    "require_dict",
    "require_key",
]


# --------------------------------------------------------------------------
# Omission sentinel (schema §5.3)
# --------------------------------------------------------------------------

class Omitted:
    """The type of the `OMIT` sentinel. Never instantiated more than
    once (see `OMIT` below); exists as a distinct type, rather than
    reusing `None`, precisely because schema §5.3 requires `None` to
    remain available and meaningful for the schema's one
    "Required, nullable" field (`parent_id` at the chapter root). A
    value can be "optional and absent" (`OMIT`) or "mandatory, no
    value" (`None`) and a type built on `json_object` can express both
    without ambiguity.
    """

    _instance: "Omitted | None" = None

    def __new__(cls) -> "Omitted":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "OMIT"

    def __bool__(self) -> bool:
        return False


OMIT = Omitted()


def json_object(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    """Build a JSON-serializable dict from (key, value) pairs, dropping
    any pair whose value is the `OMIT` sentinel while preserving an
    explicit `None` as a real JSON `null`. This is the single place
    "optional and absent" vs. "mandatory, no value" (schema §5.3) is
    decided, so every model built on top of it (this milestone's
    primitives, and every later milestone's composite models) gets
    that distinction for free instead of re-implementing it per field.

    Example:
        json_object([
            ("parent_id", None),               # explicit null, kept
            ("number", OMIT),                  # optional, absent, dropped
            ("title", "Newton's Second Law"),  # present, kept
        ])
        == {"parent_id": None, "title": "Newton's Second Law"}
    """
    return {key: value for key, value in pairs if value is not OMIT}


@runtime_checkable
class JsonSerializable(Protocol):
    """Structural contract every DST value type follows: encode itself
    to plain JSON-compatible data, and decode itself back from that
    same shape. Declared as a `Protocol` (not an ABC) so the frozen
    dataclasses this package uses (see primitives.py) satisfy it
    without inheriting from anything -- consistent with this
    codebase's existing convention of plain, storable dataclasses
    (see knowledge_graph/schema.py's own docstring on this point)."""

    def to_json(self) -> Any: ...

    @classmethod
    def from_json(cls, data: Any) -> "JsonSerializable": ...


_T = TypeVar("_T", bound=JsonSerializable)


def round_trip(instance: _T) -> Tuple[Any, _T, Any]:
    """The generic round-trip harness every primitive type's tests are
    built on (roadmap M0 deliverable): encode -> decode -> re-encode.

    Returns `(encoded_once, decoded, encoded_twice)` so a caller can
    assert both that `encoded_once == encoded_twice` (serialization is
    stable) and that `decoded == instance` (deserialization recovers
    an equal value) -- the two halves of "round-trips cleanly" that
    together prove neither direction silently loses or mutates data.
    """
    encoded_once = instance.to_json()
    decoded = type(instance).from_json(encoded_once)
    encoded_twice = decoded.to_json()
    return encoded_once, decoded, encoded_twice


# --------------------------------------------------------------------------
# Shared validators -- the "validation hooks" every §2.1 primitive type
# is built from. Each raises DSTValueError (a value that decoded fine,
# JSON-shape-wise, but fails the type's own constraint) with a message
# naming both the offending field and the constraint, per the
# milestone's "code quality / maintainability" review criteria.
# --------------------------------------------------------------------------

def require_non_empty_str(value: Any, field_name: str) -> str:
    """Every opaque string identifier in schema §2.1 (`ChapterId`,
    `NodeId`, `CanonicalObjectId`, ...) is constrained to "non-empty".
    This is the one place that constraint is enforced."""
    if not isinstance(value, str):
        raise DSTValueError(f"{field_name} must be a string, got {type(value).__name__}.")
    if value == "":
        raise DSTValueError(f"{field_name} must be a non-empty string.")
    return value


def require_non_negative_int(value: Any, field_name: str) -> int:
    """Shared by `Level` and `BlockIndex` (schema §2.1: both
    "non-negative integer"). Rejects bool explicitly even though
    `bool` is a subclass of `int` in Python, since a boolean value
    here would almost certainly indicate a caller error, not an
    intentional 0/1."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise DSTValueError(f"{field_name} must be an integer, got {type(value).__name__}.")
    if value < 0:
        raise DSTValueError(f"{field_name} must be >= 0, got {value}.")
    return value


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def require_semver(value: Any, field_name: str) -> str:
    """`SchemaVersion` and `CompilerVersion` are both "semantic-version
    strings" per schema §2.1's "Version field format" decision
    (MAJOR.MINOR.PATCH, all-numeric per that same table's examples,
    e.g. "1.1.0", "3.4.2"). Pre-release/build-metadata suffixes are
    not part of this schema's chosen format, so they are rejected
    here rather than silently accepted and later mishandled by a
    MAJOR-gating consumer (§2.3)."""
    text = require_non_empty_str(value, field_name)
    if not _SEMVER_RE.match(text):
        raise DSTValueError(
            f"{field_name} must be a MAJOR.MINOR.PATCH semantic-version "
            f"string (schema §2.1), got {text!r}."
        )
    return text


_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def require_iso8601_utc(value: Any, field_name: str) -> str:
    """`Timestamp` is "ISO-8601 UTC datetime string" per schema §2.1,
    with the schema's own example using a trailing `Z` designator
    (`2026-07-15T09:00:00Z`). Both the surface shape (regex) and
    genuine calendar validity (via `datetime.fromisoformat`, after
    normalizing `Z` to `+00:00`, the form that function accepts) are
    checked, so e.g. `2026-02-30T00:00:00Z` (not a real date) is
    rejected, not just malformed punctuation."""
    text = require_non_empty_str(value, field_name)
    if not _ISO8601_UTC_RE.match(text):
        raise DSTValueError(
            f"{field_name} must be an ISO-8601 UTC datetime string "
            f"ending in 'Z' (schema §2.1), got {text!r}."
        )
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise DSTValueError(f"{field_name} is not a valid calendar timestamp: {text!r} ({exc}).") from exc
    return text


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def require_sha256_hex(value: Any, field_name: str) -> str:
    """`Fingerprint` is "SHA-256 digest, lowercase hex string" per
    schema §2.1's "Fingerprint hash algorithm" decision. Uppercase hex
    is rejected rather than normalized, since the schema's decision is
    specifically "lowercase" -- silently lowercasing an uppercase
    digest here would hide a producer that isn't following the
    convention."""
    text = require_non_empty_str(value, field_name)
    if not _SHA256_HEX_RE.match(text):
        raise DSTValueError(
            f"{field_name} must be a 64-character lowercase hex SHA-256 "
            f"digest (schema §2.1), got {text!r}."
        )
    return text


def require_dict(data: Any, type_name: str) -> Dict[str, Any]:
    """Shared `from_json` entry-point guard for every composite (non-
    scalar) type in this package (e.g. `BlockRange`, `PageRange`,
    `Span`): the incoming JSON value must be a plain object before any
    field can be looked up. Raises DSTSerializationError, not
    DSTValueError, since this is a shape failure prior to any field's
    own constraint being checked."""
    if not isinstance(data, dict):
        raise DSTSerializationError(
            f"{type_name}.from_json expects a JSON object, got {type(data).__name__}."
        )
    return data


def require_key(data: Dict[str, Any], key: str, type_name: str) -> Any:
    """Shared "mandatory field present" guard for composite types'
    `from_json` methods. Distinguishes a genuinely missing key (a
    serialization-shape defect) from a key present with an invalid
    value (that field's own constructor's job to reject)."""
    if key not in data:
        raise DSTSerializationError(f"{type_name}.from_json: missing required key {key!r}.")
    return data[key]
