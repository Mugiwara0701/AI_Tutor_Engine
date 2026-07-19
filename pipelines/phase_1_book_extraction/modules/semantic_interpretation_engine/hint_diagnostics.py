"""
modules/semantic_interpretation_engine/hint_diagnostics.py — M5.2D
Deliverable #3: Hint Resolution Diagnostics.

Wraps M5.2C's HintResolver without modifying it.  The
HintDiagnosticsEngine calls the existing resolver, inspects its inputs
and outputs, and produces a structured HintDiagnosticsResult that
categorises every hint key as resolved, ignored, unknown, or defaulted.

M5.2C's HintResolver is NOT subclassed or monkey-patched.  This module
only imports and calls it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from modules.structural_understanding_engine.hint_resolver import HintResolver
from modules.structural_understanding_engine.hints import ResolvedHints

from modules.semantic_interpretation_engine.exceptions import HintDiagnosticsError

__all__ = [
    "HintWarning",
    "HintDiagnosticsResult",
    "HintDiagnosticsEngine",
    "default_hint_diagnostics_engine",
]

# ---------------------------------------------------------------------------
# Known hint key sets (mirrors HintResolver's _split logic)
# ---------------------------------------------------------------------------

_KNOWN_PROCESSING_KEYS: FrozenSet[str] = frozenset({"priority", "enabled"})
_KNOWN_RECOGNITION_KEYS: FrozenSet[str] = frozenset({"aliases", "confidence_threshold"})
_KNOWN_STRUCTURAL_KEYS: FrozenSet[str] = frozenset({"pattern_key", "component_aliases"})
_KNOWN_VALIDATION_KEYS: FrozenSet[str] = frozenset({"strict", "required_roles"})
_KNOWN_RELATIONSHIP_KEYS: FrozenSet[str] = frozenset({"related_keys"})

# hint namespace → known keys mapping
_NAMESPACE_KEYS: Dict[str, FrozenSet[str]] = {
    "processing_hints": _KNOWN_PROCESSING_KEYS,
    "recognition_hints": _KNOWN_RECOGNITION_KEYS,
    "structural_hints": _KNOWN_STRUCTURAL_KEYS,
    "validation_hints": _KNOWN_VALIDATION_KEYS,
    "relationship_hints": _KNOWN_RELATIONSHIP_KEYS,
}


@dataclass(frozen=True)
class HintWarning:
    """A single diagnostic warning produced during hint analysis."""

    namespace: str
    key: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"namespace": self.namespace, "key": self.key, "message": self.message}


@dataclass(frozen=True)
class HintDiagnosticsResult:
    """
    Structured report of what happened during hint resolution for a
    SubjectContribution.

    Attributes:
        resolved_hints:   The typed ResolvedHints produced by M5.2C's
                          HintResolver (reference, not copy — immutable).
        resolved_keys:    Per-namespace sets of hint keys that were
                          recognised and used.
        ignored_keys:     Per-namespace sets of hint keys present in the
                          raw input but not consumed (landed in ``extra``).
        unknown_keys:     Per-namespace sets of hint keys not belonging to
                          any known namespace.
        defaulted_keys:   Per-namespace sets of hint keys that were absent
                          from the raw input and therefore took a default.
        warnings:         Ordered tuple of HintWarning entries.
        subject_key:      The subject_key of the SubjectContribution.
        object_type_key:  The object type key of the SubjectContribution.
    """

    resolved_hints: ResolvedHints
    resolved_keys: Mapping[str, Tuple[str, ...]]
    ignored_keys: Mapping[str, Tuple[str, ...]]
    unknown_keys: Mapping[str, Tuple[str, ...]]
    defaulted_keys: Mapping[str, Tuple[str, ...]]
    warnings: Tuple[HintWarning, ...]
    subject_key: str = ""
    object_type_key: str = ""

    def __post_init__(self) -> None:
        # Freeze inner tuples so the whole structure is truly immutable.
        object.__setattr__(self, "resolved_keys", {k: tuple(v) for k, v in self.resolved_keys.items()})
        object.__setattr__(self, "ignored_keys", {k: tuple(v) for k, v in self.ignored_keys.items()})
        object.__setattr__(self, "unknown_keys", {k: tuple(v) for k, v in self.unknown_keys.items()})
        object.__setattr__(self, "defaulted_keys", {k: tuple(v) for k, v in self.defaulted_keys.items()})
        object.__setattr__(self, "warnings", tuple(self.warnings))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "object_type_key": self.object_type_key,
            "resolved_keys": {k: list(v) for k, v in self.resolved_keys.items()},
            "ignored_keys": {k: list(v) for k, v in self.ignored_keys.items()},
            "unknown_keys": {k: list(v) for k, v in self.unknown_keys.items()},
            "defaulted_keys": {k: list(v) for k, v in self.defaulted_keys.items()},
            "warnings": [w.to_dict() for w in self.warnings],
        }


class HintDiagnosticsEngine:
    """
    Wraps M5.2C's HintResolver to produce HintDiagnosticsResult.

    Does NOT subclass or modify HintResolver.
    """

    def __init__(self, resolver: Optional[HintResolver] = None) -> None:
        self._resolver = resolver or HintResolver()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diagnose(self, contribution: Any) -> HintDiagnosticsResult:
        """
        Resolve hints from *contribution* (a SubjectContribution) and
        return a fully categorised HintDiagnosticsResult.

        Parameters
        ----------
        contribution:
            A ``modules.subject_profile_framework.models.SubjectContribution``
            instance.  Typed as ``Any`` here to avoid importing M5.2B in
            the type signature (consistent with M5.2C's HintResolver
            pattern).
        """
        try:
            resolved = self._resolver.resolve(contribution)
        except Exception as exc:
            raise HintDiagnosticsError(
                f"HintResolver failed for subject_key={getattr(contribution, 'subject_key', '?')!r}: {exc}"
            ) from exc

        raw_namespaces: Dict[str, Mapping[str, Any]] = {
            "processing_hints": dict(getattr(contribution, "processing_hints", {}) or {}),
            "recognition_hints": {},  # not a field on SubjectContribution
            "structural_hints": dict(getattr(contribution, "structural_hints", {}) or {}),
            "validation_hints": dict(getattr(contribution, "validation_hints", {}) or {}),
            "relationship_hints": dict(getattr(contribution, "relationship_hints", {}) or {}),
        }

        resolved_keys: Dict[str, list] = {}
        ignored_keys: Dict[str, list] = {}
        unknown_keys: Dict[str, list] = {}
        defaulted_keys: Dict[str, list] = {}
        warnings: list = []

        for ns, raw in raw_namespaces.items():
            known = _NAMESPACE_KEYS.get(ns, frozenset())
            res: list = []
            ign: list = []
            unk: list = []

            for k in raw:
                if k in known:
                    res.append(k)
                else:
                    ign.append(k)
                    warnings.append(
                        HintWarning(
                            namespace=ns,
                            key=k,
                            message=f"Key {k!r} in {ns!r} is not a recognised hint key and will be passed to 'extra'.",
                        )
                    )

            # defaulted = known keys that were NOT present in raw
            dfl = [k for k in known if k not in raw]

            resolved_keys[ns] = res
            ignored_keys[ns] = ign
            unknown_keys[ns] = unk
            defaulted_keys[ns] = dfl

        return HintDiagnosticsResult(
            resolved_hints=resolved,
            resolved_keys=resolved_keys,
            ignored_keys=ignored_keys,
            unknown_keys=unknown_keys,
            defaulted_keys=defaulted_keys,
            warnings=tuple(warnings),
            subject_key=getattr(contribution, "subject_key", ""),
            object_type_key=getattr(contribution.object_type, "key", "")
            if hasattr(contribution, "object_type")
            else "",
        )


#: Module-level singleton for convenience.
default_hint_diagnostics_engine = HintDiagnosticsEngine()
