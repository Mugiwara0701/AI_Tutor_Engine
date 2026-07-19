"""
modules/structural_understanding_engine/engine.py — M5.2C: the
Structural Understanding Engine itself.

Deterministic orchestration over the rest of this package:
`HintResolver` (raw M5.2B hints -> typed M5.2C hints),
`patterns.StructuralPatternRegistry` (which shape a `StructuralObject`
should match), and M5.1's own `ValidationResult` contracts (how a
match's completeness is reported). Performs no semantic enrichment,
relationship discovery, copyright normalization, or LLM integration —
see this package's README.md "Out of Scope".
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from modules.educational_object_framework.enums import DiagnosticSeverity
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)
from modules.structural_understanding_engine.enums import AnalysisOutcome
from modules.structural_understanding_engine.exceptions import StructuralAnalysisError
from modules.structural_understanding_engine.hint_resolver import HintResolver, default_resolver
from modules.structural_understanding_engine.hints import ResolvedHints
from modules.structural_understanding_engine.patterns import (
    StructuralPattern,
    StructuralPatternRegistry,
    default_structural_patterns,
)
from modules.structural_understanding_engine.structural_models import (
    StructuralAnalysisResult,
    StructuralObject,
)

if TYPE_CHECKING:
    from modules.subject_profile_framework.models import SubjectContribution


def _resolve_role(role: str, component_aliases: dict, components: dict) -> Optional[str]:
    """Returns the *key actually present* in `components` for a given
    canonical `role`, checking the role itself first and then any
    subject-profile-declared alias for it. Returns `None` if neither is
    present."""
    if role in components:
        return role
    alias = component_aliases.get(role)
    if alias is not None and alias in components:
        return alias
    return None


class StructuralUnderstandingEngine:
    """Deterministically matches a `StructuralObject` against a known
    `StructuralPattern` and reports how complete that match is.

    Stateless across calls other than the registries it was
    constructed with (both of which it only reads) — a single instance
    is safe to reuse or share, mirroring every sibling framework's own
    "reuse singleton components" convention (M5.1's own performance
    requirement).
    """

    def __init__(
        self,
        pattern_registry: StructuralPatternRegistry = default_structural_patterns,
        hint_resolver: HintResolver = default_resolver,
    ) -> None:
        self._patterns = pattern_registry
        self._hint_resolver = hint_resolver

    @property
    def patterns(self) -> StructuralPatternRegistry:
        return self._patterns

    def resolve_hints(self, contribution: "SubjectContribution") -> ResolvedHints:
        """Thin pass-through to this engine's own `HintResolver` — the
        engine never reads a `SubjectContribution`'s raw hint mappings
        directly, only through this resolver."""
        return self._hint_resolver.resolve(contribution)

    def resolve_pattern(
        self,
        structural_object: StructuralObject,
        resolved_hints: Optional[ResolvedHints] = None,
    ) -> Optional[StructuralPattern]:
        """Determines which `StructuralPattern` applies to
        `structural_object`, preferring (in order): an explicit
        `StructuralObject.pattern_key`, then
        `ResolvedHints.structural.pattern_key` (if `resolved_hints` was
        supplied), then `StructuralObject.object_type_key` itself (many
        taxonomy keys already coincide with a pattern key). Returns
        `None` if nothing resolves."""
        candidates = [structural_object.pattern_key]
        if resolved_hints is not None:
            candidates.append(resolved_hints.structural.pattern_key)
        candidates.append(structural_object.object_type_key)

        for candidate in candidates:
            if candidate and candidate in self._patterns:
                return self._patterns.get(candidate)
        return None

    def analyze(
        self,
        structural_object: StructuralObject,
        resolved_hints: Optional[ResolvedHints] = None,
    ) -> StructuralAnalysisResult:
        """Deterministically analyzes `structural_object`'s structural
        completeness. Never mutates `structural_object`. Never raises
        for an ordinary "pattern not found" or "components missing"
        outcome — those are reported via `AnalysisOutcome` /
        `ValidationResult`, not exceptions; only a malformed argument
        raises `StructuralAnalysisError`."""
        if not isinstance(structural_object, StructuralObject):
            raise StructuralAnalysisError(
                f"analyze() requires a StructuralObject, got {type(structural_object).__name__}."
            )

        pattern = self.resolve_pattern(structural_object, resolved_hints)
        if pattern is None:
            return StructuralAnalysisResult(
                object_key=structural_object.object_key,
                pattern_key=None,
                outcome=AnalysisOutcome.UNRECOGNIZED_PATTERN,
                validation=ValidationResult(
                    diagnostics=(
                        ValidationDiagnostic(
                            severity=DiagnosticSeverity.ERROR,
                            code="structural.unrecognized_pattern",
                            message=(
                                f"No structural pattern could be resolved for object "
                                f"'{structural_object.object_key}' (object_type "
                                f"'{structural_object.object_type_key}')."
                            ),
                        ),
                    )
                ),
            )

        component_aliases = dict(resolved_hints.structural.component_aliases) if resolved_hints else {}
        components = structural_object.components

        present_roles = []
        missing_roles = []
        # additional required roles a subject profile's own
        # ValidationHints declares, beyond whatever the pattern itself
        # marks required — union'd, never subtracted, so a profile can
        # only tighten requirements, never loosen the pattern's own.
        extra_required = set(resolved_hints.validation.required_roles) if resolved_hints else set()
        required_roles = set(pattern.required_roles()) | extra_required

        for role in pattern.roles():
            found_key = _resolve_role(role, component_aliases, components)
            if found_key is not None:
                present_roles.append(role)
            elif role in required_roles:
                missing_roles.append(role)
        # required roles named only via ValidationHints (not part of
        # the pattern's own component list at all) are still checked,
        # so a subject profile can require a role the base pattern
        # doesn't declare.
        for role in sorted(extra_required - set(pattern.roles())):
            found_key = _resolve_role(role, component_aliases, components)
            if found_key is None:
                missing_roles.append(role)

        if not missing_roles:
            return StructuralAnalysisResult(
                object_key=structural_object.object_key,
                pattern_key=pattern.pattern_key,
                outcome=AnalysisOutcome.COMPLETE,
                present_roles=tuple(present_roles),
                missing_roles=(),
                validation=SUCCESS,
            )

        strict = True
        if resolved_hints is not None and resolved_hints.validation.strict is not None:
            strict = resolved_hints.validation.strict
        severity = DiagnosticSeverity.ERROR if strict else DiagnosticSeverity.WARNING

        diagnostics = tuple(
            ValidationDiagnostic(
                severity=severity,
                code="structural.missing_required_component",
                message=(
                    f"Object '{structural_object.object_key}' (pattern '{pattern.pattern_key}') "
                    f"is missing required component '{role}'."
                ),
            )
            for role in missing_roles
        )
        return StructuralAnalysisResult(
            object_key=structural_object.object_key,
            pattern_key=pattern.pattern_key,
            outcome=AnalysisOutcome.INCOMPLETE,
            present_roles=tuple(present_roles),
            missing_roles=tuple(missing_roles),
            validation=ValidationResult(diagnostics=diagnostics),
        )


#: Stateless — a single shared instance, built from the shared default
#: pattern registry and hint resolver, is safe to reuse across the
#: whole process, mirroring every sibling framework's own
#: "singleton-friendly, but never required" convention.
default_engine = StructuralUnderstandingEngine()


def analyze(
    structural_object: StructuralObject,
    resolved_hints: Optional[ResolvedHints] = None,
) -> StructuralAnalysisResult:
    return default_engine.analyze(structural_object, resolved_hints)


__all__ = [
    "StructuralUnderstandingEngine",
    "default_engine",
    "analyze",
]
