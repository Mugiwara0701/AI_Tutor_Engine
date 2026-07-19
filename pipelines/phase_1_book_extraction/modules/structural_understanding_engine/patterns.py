"""
modules/structural_understanding_engine/patterns.py — M5.2C: the
catalog of known structural patterns (Worked Example, Experiment,
Proof, Derivation, Definition, Figure, Table, ...) an educational
object's internal structure may follow, plus the registry that tracks
them.

A `StructuralPattern` describes *shape* only — an ordered sequence of
named, typed `StructuralComponent` roles a `StructuralObject` of this
pattern is expected to provide (e.g. Worked Example: problem ->
solution_steps -> answer). Nothing here inspects or extracts content;
that is `engine.StructuralUnderstandingEngine`'s job, working from
whatever `StructuralObject.components` a caller already supplied.

Mirrors `modules.educational_taxonomy.registry.TaxonomyRegistry`'s own
shape (a small stateful registry class, a module-level default
instance, plain-function ergonomics) applied to structural patterns
instead of taxonomy entries — a deliberately separate, narrower
registry type, since a pattern has no lifecycle state and nothing to
execute, exactly the same reasoning `TaxonomyRegistry`'s own docstring
gives for being separate from `ProcessorRegistry`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from modules.structural_understanding_engine.exceptions import StructuralPatternError

#: Canonical key form: lowercase snake_case — same shape
#: `EducationalObjectType.key` (M5.2A) and `SubjectProfile.subject_key`
#: (M5.2B) already enforce, applied to pattern keys and component
#: roles instead.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

DEFAULT_PATTERN_VERSION: str = "1.0.0"


def _validate_key(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise StructuralPatternError(f"{field_name} must be a non-empty string.")
    if not _KEY_PATTERN.match(value):
        raise StructuralPatternError(
            f"{field_name} {value!r} must be lowercase snake_case (e.g. 'worked_example')."
        )


@dataclass(frozen=True)
class StructuralComponent:
    """One named role within a `StructuralPattern`'s ordered sequence
    (e.g. "problem", "solution_steps", "answer" within
    `worked_example`).

    Attributes:
        role: Canonical, stable, machine-readable identifier for this
            component within its pattern — lowercase snake_case.
        display_name: Human-readable label (e.g. "Solution Steps").
        order: Position of this component within its pattern's
            sequence (0-indexed); `StructuralPattern.__post_init__`
            enforces these are contiguous and unique per pattern.
        required: Whether a `StructuralObject` of this pattern must
            supply this component for
            `StructuralUnderstandingEngine.analyze()` to report the
            pattern as structurally complete.
    """

    role: str
    display_name: str
    order: int
    required: bool = True

    def __post_init__(self) -> None:
        _validate_key(self.role, field_name="StructuralComponent.role")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise StructuralPatternError("StructuralComponent.display_name must be a non-empty string.")
        if not isinstance(self.order, int) or isinstance(self.order, bool) or self.order < 0:
            raise StructuralPatternError("StructuralComponent.order must be a non-negative int.")
        if not isinstance(self.required, bool):
            raise StructuralPatternError("StructuralComponent.required must be a bool.")

    def to_dict(self) -> Dict[str, object]:
        return {
            "role": self.role,
            "display_name": self.display_name,
            "order": self.order,
            "required": self.required,
        }


@dataclass(frozen=True)
class StructuralPattern:
    """One canonical structural shape in the M5.2C pattern catalog.

    Attributes:
        pattern_key: Canonical, stable, machine-readable identifier
            (e.g. "worked_example", "experiment", "proof"). Identity
            of the pattern — uniqueness enforced on `pattern_key` alone
            by `StructuralPatternRegistry`.
        display_name: Human-readable label (e.g. "Worked Example").
        components: Every `StructuralComponent` this pattern is built
            from, in declaration order — `to_dict()` and
            `ordered_components()` always emit these sorted by
            `.order`, regardless of construction order, so
            serialization never depends on how a caller happened to
            list them.
        version: "MAJOR.MINOR.PATCH"-style string, mirroring every
            sibling framework's own versioning convention.
    """

    pattern_key: str
    display_name: str
    components: Tuple[StructuralComponent, ...] = field(default_factory=tuple)
    version: str = DEFAULT_PATTERN_VERSION

    def __post_init__(self) -> None:
        _validate_key(self.pattern_key, field_name="StructuralPattern.pattern_key")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise StructuralPatternError("StructuralPattern.display_name must be a non-empty string.")
        if not isinstance(self.version, str) or not self.version:
            raise StructuralPatternError("StructuralPattern.version must be a non-empty string.")
        object.__setattr__(self, "components", tuple(self.components))
        if not self.components:
            raise StructuralPatternError(
                f"StructuralPattern({self.pattern_key}) must declare at least one component."
            )
        roles_seen: Dict[str, int] = {}
        orders_seen: Dict[int, str] = {}
        for component in self.components:
            if not isinstance(component, StructuralComponent):
                raise StructuralPatternError(
                    f"StructuralPattern({self.pattern_key}).components entries must be "
                    f"StructuralComponent instances, got {type(component).__name__}."
                )
            if component.role in roles_seen:
                raise StructuralPatternError(
                    f"StructuralPattern({self.pattern_key}) declares duplicate role "
                    f"{component.role!r}."
                )
            if component.order in orders_seen:
                raise StructuralPatternError(
                    f"StructuralPattern({self.pattern_key}) has two components at order "
                    f"{component.order} ({orders_seen[component.order]!r} and {component.role!r})."
                )
            roles_seen[component.role] = component.order
            orders_seen[component.order] = component.role
        expected_orders = set(range(len(self.components)))
        if set(orders_seen) != expected_orders:
            raise StructuralPatternError(
                f"StructuralPattern({self.pattern_key}).components' `order` values must be "
                f"contiguous starting at 0; got {sorted(orders_seen)}."
            )

    def ordered_components(self) -> Tuple[StructuralComponent, ...]:
        return tuple(sorted(self.components, key=lambda c: c.order))

    def required_roles(self) -> Tuple[str, ...]:
        return tuple(c.role for c in self.ordered_components() if c.required)

    def roles(self) -> Tuple[str, ...]:
        return tuple(c.role for c in self.ordered_components())

    def to_dict(self) -> Dict[str, object]:
        return {
            "pattern_key": self.pattern_key,
            "display_name": self.display_name,
            "components": [c.to_dict() for c in self.ordered_components()],
            "version": self.version,
        }


class StructuralPatternRegistry:
    """Tracks every registered `StructuralPattern`, enforcing
    uniqueness of `pattern_key`. Iteration order (`all_patterns()`) is
    always deterministic — ascending `pattern_key` — regardless of
    registration order, mirroring `TaxonomyRegistry`'s own contract."""

    def __init__(self) -> None:
        self._by_key: Dict[str, StructuralPattern] = {}

    def register(self, pattern: StructuralPattern) -> None:
        if not isinstance(pattern, StructuralPattern):
            raise StructuralPatternError(f"Object {pattern!r} is not a StructuralPattern instance.")
        if pattern.pattern_key in self._by_key:
            raise StructuralPatternError(
                f"A structural pattern with pattern_key '{pattern.pattern_key}' is already "
                "registered; call unregister() first to replace it."
            )
        self._by_key[pattern.pattern_key] = pattern

    def unregister(self, pattern_key: str) -> None:
        if pattern_key not in self._by_key:
            raise StructuralPatternError(f"No structural pattern with pattern_key '{pattern_key}' is registered.")
        del self._by_key[pattern_key]

    def get(self, pattern_key: str) -> StructuralPattern:
        if pattern_key not in self._by_key:
            raise StructuralPatternError(f"No structural pattern with pattern_key '{pattern_key}' is registered.")
        return self._by_key[pattern_key]

    def all_patterns(self) -> List[StructuralPattern]:
        return [self._by_key[k] for k in sorted(self._by_key)]

    def pattern_keys(self) -> List[str]:
        return sorted(self._by_key)

    def __contains__(self, pattern_key: str) -> bool:
        return pattern_key in self._by_key

    def __len__(self) -> int:
        return len(self._by_key)


def _built_in_patterns() -> Tuple[StructuralPattern, ...]:
    """The seven structural shapes named explicitly by the M5.2C
    spec. Purely structural — no subject, no content, no processing
    logic; see this package's README.md for the full catalog
    rationale."""
    return (
        StructuralPattern(
            pattern_key="worked_example",
            display_name="Worked Example",
            components=(
                StructuralComponent("problem", "Problem", 0),
                StructuralComponent("solution_steps", "Solution Steps", 1),
                StructuralComponent("answer", "Answer", 2),
            ),
        ),
        StructuralPattern(
            pattern_key="experiment",
            display_name="Experiment",
            components=(
                StructuralComponent("objective", "Objective", 0),
                StructuralComponent("materials", "Materials", 1),
                StructuralComponent("procedure", "Procedure", 2),
                StructuralComponent("observation", "Observation", 3),
                StructuralComponent("conclusion", "Conclusion", 4),
            ),
        ),
        StructuralPattern(
            pattern_key="proof",
            display_name="Proof",
            components=(
                StructuralComponent("statement", "Statement", 0),
                StructuralComponent("reasoning", "Reasoning", 1),
                StructuralComponent("conclusion", "Conclusion", 2),
            ),
        ),
        StructuralPattern(
            pattern_key="derivation",
            display_name="Derivation",
            components=(
                StructuralComponent("ordered_steps", "Ordered Steps", 0),
                StructuralComponent("final_result", "Final Result", 1),
            ),
        ),
        StructuralPattern(
            pattern_key="definition",
            display_name="Definition",
            components=(
                StructuralComponent("term", "Term", 0),
                StructuralComponent("meaning", "Meaning", 1),
                StructuralComponent("notes", "Notes", 2, required=False),
            ),
        ),
        StructuralPattern(
            pattern_key="figure",
            display_name="Figure",
            components=(
                StructuralComponent("caption", "Caption", 0),
                StructuralComponent("labels", "Labels", 1, required=False),
                StructuralComponent("referenced_concepts", "Referenced Concepts", 2, required=False),
            ),
        ),
        StructuralPattern(
            pattern_key="table",
            display_name="Table",
            components=(
                StructuralComponent("headers", "Headers", 0),
                StructuralComponent("rows", "Rows", 1),
                StructuralComponent("columns", "Columns", 2, required=False),
                StructuralComponent("footnotes", "Footnotes", 3, required=False),
            ),
        ),
    )


def _seed(registry: StructuralPatternRegistry) -> None:
    for pattern in _built_in_patterns():
        registry.register(pattern)


# -- module-level default registry + convenience functions --------------------------------------------------

default_structural_patterns = StructuralPatternRegistry()
_seed(default_structural_patterns)


def register(pattern: StructuralPattern) -> None:
    default_structural_patterns.register(pattern)


def unregister(pattern_key: str) -> None:
    default_structural_patterns.unregister(pattern_key)


def get(pattern_key: str) -> StructuralPattern:
    return default_structural_patterns.get(pattern_key)


def all_patterns() -> List[StructuralPattern]:
    return default_structural_patterns.all_patterns()


__all__ = [
    "DEFAULT_PATTERN_VERSION",
    "StructuralComponent",
    "StructuralPattern",
    "StructuralPatternRegistry",
    "default_structural_patterns",
    "register",
    "unregister",
    "get",
    "all_patterns",
]
