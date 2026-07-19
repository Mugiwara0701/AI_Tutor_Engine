"""
modules/educational_object_framework/pipeline.py — M5.1: deterministic
processor execution pipeline.

Runs every enabled, applicable processor in a `ProcessorRegistry`
against the SAME `ProcessingContext` (in the registry's own
deterministic priority order — see
`ProcessorRegistry.all_processors()`), collecting each processor's
outcome into one aggregate `ProcessingPipelineResult`. This is the
framework's one deliberate departure from both sibling pipelines, and
worth naming explicitly:

* `heading_recognizers.pipeline.RecognitionPipeline` runs every
  recognizer against the same input and picks ONE winner —
  recognizers **compete**.
* `heading_canonicalization.pipeline.CanonicalizationPipeline` threads
  ONE evolving heading through every canonicalizer in sequence, each
  one enriching what the last one produced — canonicalizers
  **cooperate** on a shared, mutating payload.
* This pipeline instead runs every processor against the SAME,
  unchanged `ProcessingContext` and simply collects every result —
  processors **coexist**, each reporting independently. This is the
  only shape that fits M5.1's constraint of not hard-coding any
  educational object type: with no framework-level notion of "the"
  transformation an object undergoes, there is nothing for this
  pipeline to thread between processors the way
  `CanonicalizationPipeline` threads a `CanonicalHeading`. In
  practice a future M5.2 processor's own `supports()` will typically
  narrow "every processor" down to "the one processor that handles
  this `context.object_type`", but the framework itself makes no such
  assumption — nothing here prevents two processors from both
  reporting on the same object (e.g. an extraction processor and an
  independent validation processor), which is exactly the
  cooperation-without-coupling M5.1 is meant to enable for M5.2.

Nothing here knows about any concrete processor's domain logic — this
module is pure orchestration over the `EducationalObjectProcessor`
interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from modules.educational_object_framework.base import (
    EducationalObjectProcessor,
    ProcessingContext,
    ProcessingFailure,
)
from modules.educational_object_framework.config import EducationalObjectFrameworkConfig
from modules.educational_object_framework.enums import ProcessingOutcome
from modules.educational_object_framework.exceptions import ProcessorExecutionError
from modules.educational_object_framework.models import ProcessingResult
from modules.educational_object_framework.registry import ProcessorRegistry


@dataclass(frozen=True)
class AttemptRecord:
    """One processor's outcome for one pipeline run. Kept even for
    NO_RESULT/SKIPPED/FAILED outcomes (nothing is discarded here) so
    diagnostics and tests can inspect the full picture of a pipeline
    run, not just its successful results. Mirrors
    `heading_canonicalization.pipeline.AttemptRecord`, adapted to this
    framework's EXECUTED/NO_RESULT/FAILED/SKIPPED outcome set."""

    processor_name: str
    outcome: ProcessingOutcome
    result: Optional[ProcessingResult] = None
    failure: Optional[ProcessingFailure] = None

    def __post_init__(self) -> None:
        if self.outcome == ProcessingOutcome.EXECUTED and self.result is None:
            raise ValueError("AttemptRecord with outcome EXECUTED must carry a `result`.")
        if self.outcome == ProcessingOutcome.FAILED and self.failure is None:
            raise ValueError("AttemptRecord with outcome FAILED must carry a `failure`.")


@dataclass(frozen=True)
class ProcessingPipelineResult:
    """The full, deterministic outcome of running every enabled
    processor in a registry against one `ProcessingContext`.

    `context` is the context exactly as passed to `run()` — never
    mutated by this pipeline (unlike
    `CanonicalizationPipelineResult.output_heading`, there is no
    single "final" context here, since processors coexist rather than
    cooperate on one evolving payload; see this module's docstring).
    `attempts` records every processor's step, in execution order,
    regardless of outcome. `results` is the convenience subset of
    `attempts` that actually produced a `ProcessingResult`."""

    context: ProcessingContext
    attempts: Tuple[AttemptRecord, ...] = field(default_factory=tuple)

    def attempts_by_outcome(self, outcome: ProcessingOutcome) -> Tuple[AttemptRecord, ...]:
        return tuple(a for a in self.attempts if a.outcome == outcome)

    @property
    def results(self) -> Tuple[ProcessingResult, ...]:
        """Every `ProcessingResult` actually produced (outcome
        EXECUTED), in execution order — the aggregate this pipeline
        exists to build."""
        return tuple(
            a.result for a in self.attempts_by_outcome(ProcessingOutcome.EXECUTED) if a.result is not None
        )

    @property
    def successful_results(self) -> Tuple[ProcessingResult, ...]:
        """The subset of `results` where the processor itself also
        reported `success=True` — narrower than `results`, which
        includes a processor's own domain-level failures too."""
        return tuple(r for r in self.results if r.success)

    @property
    def failures(self) -> Tuple[ProcessingFailure, ...]:
        """Every `ProcessingFailure` recorded (outcome FAILED), in
        execution order — the audit trail for "what went wrong",
        without ever having aborted the run itself."""
        return tuple(
            a.failure for a in self.attempts_by_outcome(ProcessingOutcome.FAILED) if a.failure is not None
        )

    @property
    def executed_processor_names(self) -> Tuple[str, ...]:
        """Names of every processor that actually produced a result,
        in the order they ran — the audit trail for "which processors
        contributed to this context's aggregate output"."""
        return tuple(a.processor_name for a in self.attempts_by_outcome(ProcessingOutcome.EXECUTED))


class ProcessingPipeline:
    """Runs a `ProcessorRegistry`'s enabled processors against a
    `ProcessingContext` and produces a deterministic
    `ProcessingPipelineResult`. Stateless across calls — a single
    `ProcessingPipeline` instance is safe to reuse (or share) across
    any number of `run()` calls, mirroring
    `CanonicalizationPipeline`'s / `RecognitionPipeline`'s own
    statelessness contract, and satisfying the M5.1 spec's
    "reuse singleton components" performance requirement."""

    def __init__(
        self,
        registry: ProcessorRegistry,
        config: Optional[EducationalObjectFrameworkConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or registry.config

    @property
    def registry(self) -> ProcessorRegistry:
        return self._registry

    @property
    def config(self) -> EducationalObjectFrameworkConfig:
        return self._config

    def run(self, context: ProcessingContext) -> ProcessingPipelineResult:
        """Deterministically runs every enabled processor, in registry
        (priority) order, against `context`. A processor that raises
        or fails `supports()` never aborts the run — its step is
        recorded as FAILED and the pipeline simply moves on to the
        next processor, exactly mirroring
        `CanonicalizationPipeline.run()` /
        `RecognitionPipeline.run()`'s "one misbehaving component can't
        take the whole run down" guarantee. Every processor receives
        the SAME `context` (see this module's docstring for why)."""
        attempts: List[AttemptRecord] = []

        for processor in self._registry.enabled_processors():
            try:
                supported = processor.supports(context)
            except Exception as exc:  # noqa: BLE001 - mirrors safe_process()'s own deliberately broad catch
                attempts.append(AttemptRecord(
                    processor.name,
                    ProcessingOutcome.FAILED,
                    failure=ProcessingFailure(
                        processor_name=processor.name,
                        reason=f"supports() raised: {exc}",
                        exception_type=type(exc).__name__,
                    ),
                ))
                continue
            if not supported:
                attempts.append(AttemptRecord(processor.name, ProcessingOutcome.SKIPPED))
                continue

            try:
                result = processor.safe_process(context)
            except ProcessorExecutionError as exc:
                attempts.append(AttemptRecord(
                    processor.name,
                    ProcessingOutcome.FAILED,
                    failure=ProcessingFailure(
                        processor_name=processor.name,
                        reason=str(exc),
                        exception_type=type(exc.__cause__ or exc).__name__,
                    ),
                ))
                continue

            if result is None:
                attempts.append(AttemptRecord(processor.name, ProcessingOutcome.NO_RESULT))
                continue

            attempts.append(AttemptRecord(processor.name, ProcessingOutcome.EXECUTED, result=result))

        return ProcessingPipelineResult(context=context, attempts=tuple(attempts))


__all__ = [
    "AttemptRecord",
    "ProcessingPipelineResult",
    "ProcessingPipeline",
]
