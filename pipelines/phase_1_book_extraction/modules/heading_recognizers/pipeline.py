"""
modules/heading_recognizers/pipeline.py — M4.2A: deterministic
recognizer execution pipeline.

Invokes every enabled recognizer in a RecognizerRegistry (in the
registry's own deterministic priority order — see
RecognizerRegistry.all_recognizers()), collects each attempt's
outcome, applies each recognizer's own configured confidence
threshold, and resolves conflicts between recognizers that both
matched the same RecognitionContext according to the framework's
configured ConflictResolutionStrategy. Nothing here knows about any
concrete recognizer's matching logic — this module is pure
orchestration over the `HeadingRecognizer` interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from modules.heading_recognizers.base import RecognitionContext, RecognitionResult, FailureResult
from modules.heading_recognizers.config import HeadingRecognitionConfig
from modules.heading_recognizers.enums import ConflictResolutionStrategy, RecognitionOutcome
from modules.heading_recognizers.exceptions import RecognitionPipelineError, RecognizerExecutionError
from modules.heading_recognizers.registry import RecognizerRegistry
from modules.heading_recognizers.utils import meets_threshold


@dataclass(frozen=True)
class AttemptRecord:
    """One recognizer's outcome for one RecognitionContext. Kept even
    for NO_MATCH/SKIPPED/FAILED outcomes (nothing is discarded here —
    the same "every block keeps its annotation" philosophy
    stage_c_priority.py documents for its own output) so diagnostics
    and tests can inspect the full picture of a pipeline run, not just
    its winner(s)."""

    recognizer_name: str
    outcome: RecognitionOutcome
    result: Optional[RecognitionResult] = None
    failure: Optional[FailureResult] = None

    def __post_init__(self) -> None:
        if self.outcome == RecognitionOutcome.MATCHED and self.result is None:
            raise ValueError("AttemptRecord with outcome MATCHED must carry a `result`.")
        if self.outcome == RecognitionOutcome.FAILED and self.failure is None:
            raise ValueError("AttemptRecord with outcome FAILED must carry a `failure`.")


@dataclass(frozen=True)
class PipelineResult:
    """The full, deterministic outcome of running every enabled
    recognizer in a registry against one RecognitionContext.

    `matches` is every recognizer's result that both matched AND
    cleared its own configured confidence threshold, in registry
    (priority) order. `winners` is `matches` after conflict
    resolution — empty if nothing matched, exactly one entry for
    every strategy except ALL_MATCHES, which may return several.
    """

    context: RecognitionContext
    attempts: Tuple[AttemptRecord, ...] = field(default_factory=tuple)
    matches: Tuple[RecognitionResult, ...] = field(default_factory=tuple)
    winners: Tuple[RecognitionResult, ...] = field(default_factory=tuple)

    @property
    def winner(self) -> Optional[RecognitionResult]:
        """Convenience for the common case: the single best result, or
        None if nothing matched. Raises RecognitionPipelineError if
        the configured strategy is ALL_MATCHES and more than one
        result won — callers wanting every winner should read
        `.winners` directly instead of this property."""
        if not self.winners:
            return None
        if len(self.winners) > 1:
            raise RecognitionPipelineError(
                "PipelineResult.winner was accessed but multiple results won "
                "(conflict_resolution=ALL_MATCHES); use `.winners` instead."
            )
        return self.winners[0]

    def attempts_by_outcome(self, outcome: RecognitionOutcome) -> Tuple[AttemptRecord, ...]:
        return tuple(a for a in self.attempts if a.outcome == outcome)


class RecognitionPipeline:
    """Runs a RecognizerRegistry's enabled recognizers against a
    RecognitionContext and produces a deterministic PipelineResult.
    Stateless across calls — a single RecognitionPipeline instance is
    safe to reuse (or share) across any number of `run()` calls."""

    def __init__(
        self,
        registry: RecognizerRegistry,
        config: Optional[HeadingRecognitionConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or registry.config

    @property
    def registry(self) -> RecognizerRegistry:
        return self._registry

    @property
    def config(self) -> HeadingRecognitionConfig:
        return self._config

    def run(self, context: RecognitionContext) -> PipelineResult:
        attempts: List[AttemptRecord] = []
        matches: List[RecognitionResult] = []

        for recognizer in self._registry.enabled_recognizers():
            if not recognizer.supports(context):
                attempts.append(AttemptRecord(recognizer.name, RecognitionOutcome.SKIPPED))
                continue

            try:
                result = recognizer.safe_recognize(context)
            except RecognizerExecutionError as exc:
                attempts.append(AttemptRecord(
                    recognizer.name,
                    RecognitionOutcome.FAILED,
                    failure=FailureResult(
                        recognizer_name=recognizer.name,
                        reason=str(exc),
                        exception_type=type(exc.__cause__ or exc).__name__,
                    ),
                ))
                continue

            if result is None:
                attempts.append(AttemptRecord(recognizer.name, RecognitionOutcome.NO_MATCH))
                continue

            threshold = self._config.settings_for(recognizer.name).confidence_threshold
            if not meets_threshold(result.confidence, threshold):
                # Matched the pattern, but not confidently enough to
                # count as a real match at this configuration's
                # threshold. Recorded as NO_MATCH (the framework-level
                # outcome), but the low-confidence result itself is
                # preserved on the attempt for diagnostics.
                attempts.append(AttemptRecord(recognizer.name, RecognitionOutcome.NO_MATCH, result=result))
                continue

            attempts.append(AttemptRecord(recognizer.name, RecognitionOutcome.MATCHED, result=result))
            matches.append(result)

        winners = self._resolve_conflicts(tuple(matches))
        return PipelineResult(
            context=context,
            attempts=tuple(attempts),
            matches=tuple(matches),
            winners=winners,
        )

    # -- conflict resolution --------------------------------------------------

    def _priority_sort_key(self, result: RecognitionResult) -> tuple:
        """Deterministic tie-break key: configured priority (ascending
        = higher priority), then registration order — the same
        ordering RecognizerRegistry.all_recognizers() itself uses, so
        conflict resolution never contradicts registration order."""
        settings = self._config.settings_for(result.recognizer_name)
        registered_names = self._registry.registered_names()
        registration_index = (
            registered_names.index(result.recognizer_name)
            if result.recognizer_name in registered_names
            else len(registered_names)
        )
        return (settings.priority, registration_index)

    def _resolve_conflicts(self, matches: Tuple[RecognitionResult, ...]) -> Tuple[RecognitionResult, ...]:
        if not matches:
            return ()

        strategy = self._config.conflict_resolution

        if strategy == ConflictResolutionStrategy.ALL_MATCHES:
            ordered = sorted(
                matches,
                key=lambda r: (-r.confidence,) + self._priority_sort_key(r),
            )
            return tuple(ordered)

        if strategy == ConflictResolutionStrategy.FIRST_MATCH:
            # `matches` is already in registry (priority) iteration
            # order — the first entry IS the first recognizer, in that
            # order, that matched.
            return (matches[0],)

        if strategy == ConflictResolutionStrategy.PRIORITY_ORDER:
            best = min(matches, key=self._priority_sort_key)
            return (best,)

        if strategy == ConflictResolutionStrategy.HIGHEST_CONFIDENCE:
            best = min(
                matches,
                key=lambda r: (-r.confidence,) + self._priority_sort_key(r),
            )
            return (best,)

        raise RecognitionPipelineError(f"Unhandled conflict resolution strategy: {strategy!r}.")


__all__ = [
    "AttemptRecord",
    "PipelineResult",
    "RecognitionPipeline",
]
