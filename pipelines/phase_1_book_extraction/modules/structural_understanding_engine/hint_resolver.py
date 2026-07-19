"""
modules/structural_understanding_engine/hint_resolver.py — M5.2C: the
sole compatibility boundary between M5.2B's frozen
`Mapping[str, Any]` hint fields and M5.2C's strongly typed hint
models.

`SubjectContribution` (M5.2B, frozen) is never modified, and resolved
hints are never written back into it — `HintResolver.resolve()` is a
pure function: `SubjectContribution -> ResolvedHints`, called fresh
wherever needed. Nothing in this module mutates its input.

Convention this resolver establishes (documented once, here, rather
than repeated per hint model): a raw hint mapping's well-known keys
are lifted onto the typed model's named fields; every other key is
preserved verbatim in that model's own `extra` mapping. Unknown keys
are never dropped, never raise — a subject profile author is free to
carry forward-looking data M5.2C does not yet understand.
"""
from __future__ import annotations

from typing import Any, Mapping

from modules.structural_understanding_engine.hints import (
    ProcessingHints,
    RecognitionHints,
    RelationshipHints,
    ResolvedHints,
    StructuralHints,
    ValidationHints,
)

#: Well-known keys lifted onto each typed model's named fields — every
#: other key in the corresponding raw mapping lands in that model's
#: `extra` instead. Centralized here so the "what is well-known" list
#: lives in exactly one place per hint model.
_PROCESSING_KEYS = ("priority", "enabled")
_RECOGNITION_KEYS = ("aliases", "confidence_threshold")
_STRUCTURAL_KEYS = ("pattern_key", "component_aliases")
_VALIDATION_KEYS = ("strict", "required_roles")
_RELATIONSHIP_KEYS = ("related_keys",)


def _split(raw: Mapping[str, Any], known_keys: tuple) -> tuple:
    """Returns (known-key subset as kwargs dict, leftover as `extra`
    dict) — leftover excludes anything already lifted onto a named
    field."""
    known = {k: raw[k] for k in known_keys if k in raw}
    extra = {k: v for k, v in raw.items() if k not in known_keys}
    return known, extra


class HintResolver:
    """Converts one `SubjectContribution`'s raw M5.2B hint mappings
    into a `ResolvedHints` bundle of M5.2C typed hint models. Stateless
    and side-effect free — safe to share a single instance, or to
    construct a fresh one per call; both are equivalent."""

    def resolve(self, contribution) -> ResolvedHints:  # contribution: SubjectContribution
        """Resolves every relevant raw hint mapping on `contribution`
        into its typed M5.2C model. `contribution.semantic_hints` is
        deliberately never read here — semantic enrichment is out of
        scope for M5.2C (see this package's README.md)."""
        processing = self._resolve_processing(contribution.processing_hints)
        recognition = self._resolve_recognition(contribution.processing_hints)
        structural = self._resolve_structural(contribution.structural_hints)
        validation = self._resolve_validation(contribution.validation_hints)
        relationship = self._resolve_relationship(contribution.relationship_hints)
        return ResolvedHints(
            processing=processing,
            recognition=recognition,
            structural=structural,
            validation=validation,
            relationship=relationship,
        )

    @staticmethod
    def _resolve_processing(raw: Mapping[str, Any]) -> ProcessingHints:
        # The nested "recognition" sub-mapping (if present) is
        # RecognitionHints' own concern, not ProcessingHints' — excluded
        # here so it does not also land in ProcessingHints.extra.
        raw_without_recognition = {k: v for k, v in raw.items() if k != "recognition"}
        known, extra = _split(raw_without_recognition, _PROCESSING_KEYS)
        return ProcessingHints(**known, extra=extra)

    @staticmethod
    def _resolve_recognition(raw: Mapping[str, Any]) -> RecognitionHints:
        nested = raw.get("recognition", {})
        if not isinstance(nested, Mapping):
            nested = {}
        known, extra = _split(nested, _RECOGNITION_KEYS)
        if "aliases" in known:
            known = dict(known)
            known["aliases"] = tuple(known["aliases"])
        return RecognitionHints(**known, extra=extra)

    @staticmethod
    def _resolve_structural(raw: Mapping[str, Any]) -> StructuralHints:
        known, extra = _split(raw, _STRUCTURAL_KEYS)
        return StructuralHints(**known, extra=extra)

    @staticmethod
    def _resolve_validation(raw: Mapping[str, Any]) -> ValidationHints:
        known, extra = _split(raw, _VALIDATION_KEYS)
        if "required_roles" in known:
            known = dict(known)
            known["required_roles"] = tuple(known["required_roles"])
        return ValidationHints(**known, extra=extra)

    @staticmethod
    def _resolve_relationship(raw: Mapping[str, Any]) -> RelationshipHints:
        known, extra = _split(raw, _RELATIONSHIP_KEYS)
        if "related_keys" in known:
            known = dict(known)
            known["related_keys"] = tuple(known["related_keys"])
        return RelationshipHints(**known, extra=extra)


#: Stateless — a single shared instance is safe to reuse across the
#: whole process, mirroring every sibling framework's own
#: "singleton-friendly, but never required" convention.
default_resolver = HintResolver()


def resolve(contribution) -> ResolvedHints:
    return default_resolver.resolve(contribution)


__all__ = [
    "HintResolver",
    "default_resolver",
    "resolve",
]
