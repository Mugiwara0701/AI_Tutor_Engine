"""
modules/heading_canonicalization/pipeline.py — M4.3A: deterministic
canonicalization execution pipeline.

Threads ONE `CanonicalHeading` through every enabled canonicalizer in
a `CanonicalizerRegistry` (in the registry's own deterministic
priority order — see `CanonicalizerRegistry.all_canonicalizers()`),
collecting each step's outcome and letting each canonicalizer's output
become the next canonicalizer's input. This is the key structural
difference from `heading_recognizers.pipeline.RecognitionPipeline`:
that pipeline runs every recognizer against the SAME input and picks
one winner (recognizers compete); this pipeline runs every
canonicalizer against a heading that a PRIOR canonicalizer may already
have updated, and every applicable one contributes (canonicalizers
cooperate). Nothing here knows about any concrete canonicalizer's
transformation logic — this module is pure orchestration over the
`HeadingCanonicalizer` interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from modules.heading_canonicalization.base import (
    CanonicalizationContext,
    CanonicalizationFailure,
    HeadingCanonicalizer,
)
from modules.heading_canonicalization.config import HeadingCanonicalizationConfig
from modules.heading_canonicalization.enums import CanonicalizationOutcome
from modules.heading_canonicalization.exceptions import CanonicalizerExecutionError
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.registry import CanonicalizerRegistry


@dataclass(frozen=True)
class AttemptRecord:
    """One canonicalizer's outcome for one step of a pipeline run.
    Kept even for UNCHANGED/SKIPPED/FAILED outcomes (nothing is
    discarded here) so diagnostics and tests can inspect the full
    picture of a pipeline run, not just its final heading. Mirrors
    `heading_recognizers.pipeline.AttemptRecord`, adapted to
    canonicalization's APPLIED/UNCHANGED/FAILED/SKIPPED outcome set."""

    canonicalizer_name: str
    outcome: CanonicalizationOutcome
    heading: Optional[CanonicalHeading] = None
    failure: Optional[CanonicalizationFailure] = None

    def __post_init__(self) -> None:
        if self.outcome == CanonicalizationOutcome.APPLIED and self.heading is None:
            raise ValueError("AttemptRecord with outcome APPLIED must carry a `heading`.")
        if self.outcome == CanonicalizationOutcome.FAILED and self.failure is None:
            raise ValueError("AttemptRecord with outcome FAILED must carry a `failure`.")


@dataclass(frozen=True)
class CanonicalizationPipelineResult:
    """The full, deterministic outcome of running every enabled
    canonicalizer in a registry against one `CanonicalHeading`.

    `input_heading` is the heading exactly as passed to `run()`.
    `output_heading` is that same heading after every enabled,
    applicable canonicalizer has had a chance to update it in
    priority order — the final state to hand to the next stage of the
    overall pipeline (or, in M4.3A, to a test). `attempts` records
    every canonicalizer's step, in execution order, regardless of
    outcome."""

    context: CanonicalizationContext
    input_heading: CanonicalHeading
    output_heading: CanonicalHeading
    attempts: Tuple[AttemptRecord, ...] = field(default_factory=tuple)

    def attempts_by_outcome(self, outcome: CanonicalizationOutcome) -> Tuple[AttemptRecord, ...]:
        return tuple(a for a in self.attempts if a.outcome == outcome)

    @property
    def applied_canonicalizer_names(self) -> Tuple[str, ...]:
        """Names of every canonicalizer that actually changed the
        heading, in the order they ran — the audit trail for "how did
        `output_heading` end up the way it did"."""
        return tuple(a.canonicalizer_name for a in self.attempts_by_outcome(CanonicalizationOutcome.APPLIED))


class CanonicalizationPipeline:
    """Runs a `CanonicalizerRegistry`'s enabled canonicalizers against
    a `CanonicalHeading` and produces a deterministic
    `CanonicalizationPipelineResult`. Stateless across calls — a
    single `CanonicalizationPipeline` instance is safe to reuse (or
    share) across any number of `run()` calls, mirroring
    `RecognitionPipeline`'s own statelessness contract."""

    def __init__(
        self,
        registry: CanonicalizerRegistry,
        config: Optional[HeadingCanonicalizationConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or registry.config

    @property
    def registry(self) -> CanonicalizerRegistry:
        return self._registry

    @property
    def config(self) -> HeadingCanonicalizationConfig:
        return self._config

    def run(
        self,
        heading: CanonicalHeading,
        context: Optional[CanonicalizationContext] = None,
    ) -> CanonicalizationPipelineResult:
        """Deterministically applies every enabled canonicalizer, in
        registry (priority) order, to `heading`. A canonicalizer that
        raises or fails `supports()` never aborts the run — its step
        is recorded as FAILED and the heading simply carries forward
        unchanged into the next canonicalizer, exactly mirroring
        `RecognitionPipeline.run()`'s "one misbehaving component can't
        take the whole run down" guarantee."""
        ctx = context if context is not None else CanonicalizationContext()
        current = heading
        attempts: List[AttemptRecord] = []

        for canonicalizer in self._registry.enabled_canonicalizers():
            try:
                supported = canonicalizer.supports(current, ctx)
            except Exception as exc:  # noqa: BLE001 - mirrors safe_canonicalize()'s own deliberately broad catch
                attempts.append(AttemptRecord(
                    canonicalizer.name,
                    CanonicalizationOutcome.FAILED,
                    failure=CanonicalizationFailure(
                        canonicalizer_name=canonicalizer.name,
                        reason=f"supports() raised: {exc}",
                        exception_type=type(exc).__name__,
                    ),
                ))
                continue
            if not supported:
                attempts.append(AttemptRecord(canonicalizer.name, CanonicalizationOutcome.SKIPPED))
                continue

            try:
                updated = canonicalizer.safe_canonicalize(current, ctx)
            except CanonicalizerExecutionError as exc:
                attempts.append(AttemptRecord(
                    canonicalizer.name,
                    CanonicalizationOutcome.FAILED,
                    failure=CanonicalizationFailure(
                        canonicalizer_name=canonicalizer.name,
                        reason=str(exc),
                        exception_type=type(exc.__cause__ or exc).__name__,
                    ),
                ))
                continue

            if updated is None:
                attempts.append(AttemptRecord(canonicalizer.name, CanonicalizationOutcome.UNCHANGED))
                continue

            attempts.append(AttemptRecord(canonicalizer.name, CanonicalizationOutcome.APPLIED, heading=updated))
            current = updated

        return CanonicalizationPipelineResult(
            context=ctx,
            input_heading=heading,
            output_heading=current,
            attempts=tuple(attempts),
        )


__all__ = [
    "AttemptRecord",
    "CanonicalizationPipelineResult",
    "CanonicalizationPipeline",
]
