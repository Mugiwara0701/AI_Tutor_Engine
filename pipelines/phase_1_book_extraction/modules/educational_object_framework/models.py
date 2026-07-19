"""
modules/educational_object_framework/models.py — M5.1: the immutable
processing result model every concrete processor's `process()`
returns.

Design note — why this is a result model, not an evolving payload
(the one deliberate asymmetry vs. `heading_canonicalization.models`):
`heading_canonicalization.CanonicalHeading` is the payload itself —
one heading flows through every canonicalizer in sequence, each one
progressively enriching the SAME object. This framework cannot do
that: M5.1 has no concrete educational object type to progressively
enrich (the spec is explicit that the context "should not assume any
specific object" and that object-specific processors are M5.2's job).
So a processor here instead produces a `ProcessingResult` — a report
about `ProcessingContext.current_object`, not a replacement for it —
and `ProcessingPipeline` aggregates every processor's report rather
than threading a mutated object through the chain (see `pipeline.py`
for the full rationale). A later milestone that DOES want to
progressively transform `current_object` can build that on top of
this framework (e.g. a processor whose `ProcessingResult.metadata`
carries the transformed object) without any change here.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Tuple

from modules.educational_object_framework.exceptions import ProcessingResultValidationError


def _frozen_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Defensive-copy helper, identical in spirit to
    `base._frozen_mapping` — kept as a private duplicate rather than
    a cross-module import so each module in this package stays
    independently readable, matching the sibling frameworks'
    convention."""
    return dict(value) if value else {}


@dataclass(frozen=True)
class ProcessingResult:
    """What a processor's `process()` returns when it has something
    to report for a given `ProcessingContext`. Immutable — once
    produced, a result flowing through pipeline aggregation cannot be
    altered by a later processor or by the pipeline itself.

    Attributes:
        processor_name: Which processor produced this result. Always
            non-empty (validated below) so a `ProcessingResult` is
            never ambiguous about its origin, even after being
            collected into an aggregate.
        success: Whether this processor considers its own processing
            of `current_object` to have succeeded. Distinct from the
            pipeline-level FAILED outcome (which means the processor
            *raised* — see `enums.ProcessingOutcome`): a processor can
            run to completion and still report `success=False` for a
            domain reason of its own (e.g. "recognized this as an
            equation but could not extract a LaTeX form").
        object_type: Echoes the kind of educational object this
            result concerns, if the processor determined or was given
            one — purely informational, same "hint, never a trigger"
            convention as `ProcessingContext.object_type`.
        diagnostics: Free-form, human-readable notes produced by this
            processor's run (e.g. "no LaTeX form found, falling back
            to plain text"). Never parsed by the framework itself —
            purely for humans and tests.
        metadata: Free-form, processor-specific output payload (e.g.
            extracted fields, confidence scores, a transformed
            object). Opaque to the framework — never inspected by
            anything in this package.
        execution_metadata: Free-form, processor-agnostic information
            about the execution itself (e.g. which sub-strategy ran,
            how many attempts it took) — kept separate from
            `metadata` so a caller can distinguish "what this
            processor found" from "how it went about finding it"
            without the two colliding under one key.
    """

    processor_name: str
    success: bool = True
    object_type: Optional[str] = None
    diagnostics: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    execution_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.processor_name, str) or not self.processor_name.strip():
            raise ProcessingResultValidationError(
                "ProcessingResult.processor_name must be a non-empty string."
            )
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))
        object.__setattr__(self, "execution_metadata", _frozen_mapping(self.execution_metadata))

    # -- immutable "update" helpers --------------------------------------------------

    def with_updates(self, **changes: Any) -> "ProcessingResult":
        """Returns a new `ProcessingResult` with `changes` applied;
        every other field is copied unchanged. Mirrors
        `CanonicalHeading.with_updates()`."""
        return replace(self, **changes)

    def with_diagnostic(self, message: str) -> "ProcessingResult":
        """Returns a new `ProcessingResult` with `message` appended to
        `diagnostics`. Convenience wrapper around `with_updates()` for
        the single most common per-step update."""
        return self.with_updates(diagnostics=self.diagnostics + (message,))

    def with_metadata(self, **changes: Any) -> "ProcessingResult":
        """Returns a new `ProcessingResult` with `metadata` merged
        (added or overwritten); every other field is copied
        unchanged."""
        merged = dict(self.metadata)
        merged.update(changes)
        return self.with_updates(metadata=merged)


__all__ = [
    "ProcessingResult",
]
