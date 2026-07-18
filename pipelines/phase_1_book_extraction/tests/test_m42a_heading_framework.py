"""
tests/test_m42a_heading_framework.py — M4.2A unit tests for
modules/heading_recognizers (the heading recognition FRAMEWORK: no
concrete recognizer is implemented in M4.2A, so these tests exercise
the framework itself against small test-double recognizers defined
in this file).

Coverage:
  - enums: membership / string-value contracts
  - exceptions: hierarchy relationships
  - config: RecognizerSettings / HeadingRecognitionConfig validation,
    immutability, settings_for() defaulting, with_* helpers
  - base: RecognitionContext / RecognitionResult / FailureResult /
    ConfidenceInfo validation and immutability; HeadingRecognizer
    safe_recognize() exception wrapping; supports() default
  - registry: registration, duplicate rejection, validation failures,
    lookup errors, enable/disable/mark_failed lifecycle, deterministic
    priority + registration-order ordering, with_config()
  - factory: register_class (class and builder forms), create(),
    name-mismatch detection, create_all(), build_registry()
  - pipeline: MATCHED / NO_MATCH / FAILED / SKIPPED outcomes,
    below-threshold-is-NO_MATCH, all four conflict resolution
    strategies, deterministic output across repeated runs
  - utils: roman numeral round-trip + validation, hierarchical number
    parsing/compare, alphabetic markers, whitespace/punctuation
    helpers, confidence combination/clamping
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_recognizers.base import (
    ConfidenceInfo,
    FailureResult,
    HeadingRecognizer,
    RecognitionContext,
    RecognitionResult,
)
from modules.heading_recognizers.config import (
    HeadingRecognitionConfig,
    RecognizerSettings,
    default_config,
)
from modules.heading_recognizers.enums import (
    ConflictResolutionStrategy,
    HeadingClassification,
    RecognitionOutcome,
    RecognizerState,
)
from modules.heading_recognizers.exceptions import (
    HeadingRecognitionError,
    RecognitionPipelineError,
    RecognizerConfigurationError,
    RecognizerExecutionError,
    RecognizerLookupError,
    RecognizerRegistrationError,
)
from modules.heading_recognizers.factory import RecognizerFactory
from modules.heading_recognizers.pipeline import RecognitionPipeline
from modules.heading_recognizers.registry import RecognizerRegistry
from modules.heading_recognizers import utils as hr_utils


# ===========================================================================
# Test doubles — NOT concrete recognizers (those are out of M4.2A's scope).
# Small, deterministic stand-ins used only to exercise the framework.
# ===========================================================================

class _AlwaysMatchRecognizer(HeadingRecognizer):
    """Matches every context with a fixed confidence."""

    def __init__(self, name: str = "always_match", confidence: float = 0.9,
                 classification: HeadingClassification = HeadingClassification.NUMBERED,
                 settings: Optional[RecognizerSettings] = None) -> None:
        self.name = name
        self.classification = classification
        self._confidence = confidence

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        return RecognitionResult(
            recognizer_name=self.name,
            classification=self.classification,
            confidence=self._confidence,
            level=1,
            title=context.text,
        )


class _NeverMatchRecognizer(HeadingRecognizer):
    def __init__(self, name: str = "never_match", settings: Optional[RecognizerSettings] = None) -> None:
        self.name = name
        self.classification = HeadingClassification.UNCLASSIFIED

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        return None


class _ExplodingRecognizer(HeadingRecognizer):
    def __init__(self, name: str = "exploding", settings: Optional[RecognizerSettings] = None) -> None:
        self.name = name
        self.classification = HeadingClassification.UNCLASSIFIED

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        raise ValueError("boom")


class _UnsupportedRecognizer(HeadingRecognizer):
    """supports() always False — recognize() should never be called."""

    def __init__(self, name: str = "unsupported", settings: Optional[RecognizerSettings] = None) -> None:
        self.name = name
        self.classification = HeadingClassification.UNCLASSIFIED

    def supports(self, context: RecognitionContext) -> bool:
        return False

    def recognize(self, context: RecognitionContext) -> Optional[RecognitionResult]:
        raise AssertionError("recognize() must not be called when supports() is False")


def _ctx(text: str = "1. Introduction") -> RecognitionContext:
    return RecognitionContext(text=text, page=1, line_index=0)


# ===========================================================================
# 1. Enums
# ===========================================================================

class TestEnums(unittest.TestCase):
    def test_heading_classification_values(self):
        self.assertEqual(HeadingClassification.NUMBERED.value, "numbered")
        self.assertEqual(HeadingClassification.CHAPTER_TITLE.value, "chapter_title")
        self.assertEqual(HeadingClassification.UNCLASSIFIED.value, "unclassified")

    def test_conflict_resolution_values(self):
        self.assertEqual(ConflictResolutionStrategy.HIGHEST_CONFIDENCE.value, "highest_confidence")
        self.assertEqual(ConflictResolutionStrategy.ALL_MATCHES.value, "all_matches")

    def test_recognizer_state_values(self):
        self.assertEqual(RecognizerState.ENABLED.value, "enabled")
        self.assertEqual(RecognizerState.FAILED.value, "failed")

    def test_recognition_outcome_values(self):
        self.assertEqual(RecognitionOutcome.MATCHED.value, "matched")
        self.assertEqual(RecognitionOutcome.SKIPPED.value, "skipped")

    def test_enums_are_string_comparable(self):
        self.assertEqual(HeadingClassification.NUMBERED, "numbered")


# ===========================================================================
# 2. Exceptions
# ===========================================================================

class TestExceptions(unittest.TestCase):
    def test_hierarchy(self):
        for exc_cls in (
            RecognizerRegistrationError,
            RecognizerConfigurationError,
            RecognizerLookupError,
            RecognizerExecutionError.__mro__[0],
            RecognitionPipelineError,
        ):
            self.assertTrue(issubclass(exc_cls, HeadingRecognitionError))

    def test_lookup_error_is_also_lookuperror(self):
        self.assertTrue(issubclass(RecognizerLookupError, LookupError))

    def test_execution_error_message(self):
        err = RecognizerExecutionError("my_recognizer", "bad regex")
        self.assertIn("my_recognizer", str(err))
        self.assertIn("bad regex", str(err))
        self.assertEqual(err.recognizer_name, "my_recognizer")


# ===========================================================================
# 3. Config
# ===========================================================================

class TestRecognizerSettings(unittest.TestCase):
    def test_defaults(self):
        settings = RecognizerSettings(name="foo")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.priority, 100)
        self.assertEqual(settings.confidence_threshold, 0.5)

    def test_empty_name_rejected(self):
        with self.assertRaises(RecognizerConfigurationError):
            RecognizerSettings(name="")

    def test_threshold_out_of_range_rejected(self):
        with self.assertRaises(RecognizerConfigurationError):
            RecognizerSettings(name="foo", confidence_threshold=1.5)
        with self.assertRaises(RecognizerConfigurationError):
            RecognizerSettings(name="foo", confidence_threshold=-0.1)

    def test_non_int_priority_rejected(self):
        with self.assertRaises(RecognizerConfigurationError):
            RecognizerSettings(name="foo", priority="high")  # type: ignore[arg-type]

    def test_is_frozen(self):
        settings = RecognizerSettings(name="foo")
        with self.assertRaises(Exception):
            settings.name = "bar"  # type: ignore[misc]

    def test_with_overrides_returns_new_instance(self):
        settings = RecognizerSettings(name="foo", priority=10)
        updated = settings.with_overrides(priority=20)
        self.assertEqual(settings.priority, 10)
        self.assertEqual(updated.priority, 20)
        self.assertEqual(updated.name, "foo")

    def test_extra_mapping_copied_defensively(self):
        source = {"k": "v"}
        settings = RecognizerSettings(name="foo", extra=source)
        source["k"] = "mutated"
        self.assertEqual(settings.extra["k"], "v")


class TestHeadingRecognitionConfig(unittest.TestCase):
    def test_default_config_is_valid(self):
        cfg = default_config()
        self.assertEqual(cfg.global_confidence_threshold, 0.5)
        self.assertEqual(cfg.conflict_resolution, ConflictResolutionStrategy.HIGHEST_CONFIDENCE)

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(RecognizerConfigurationError):
            HeadingRecognitionConfig(global_confidence_threshold=2.0)

    def test_invalid_strategy_type_rejected(self):
        with self.assertRaises(RecognizerConfigurationError):
            HeadingRecognitionConfig(conflict_resolution="highest_confidence")  # type: ignore[arg-type]

    def test_settings_for_unknown_recognizer_returns_default(self):
        cfg = default_config(global_confidence_threshold=0.7)
        settings = cfg.settings_for("never_configured")
        self.assertEqual(settings.name, "never_configured")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.confidence_threshold, 0.7)

    def test_settings_for_configured_recognizer(self):
        custom = RecognizerSettings(name="foo", enabled=False, priority=5)
        cfg = default_config(recognizer_settings={"foo": custom})
        self.assertIs(cfg.settings_for("foo"), custom)

    def test_with_recognizer_settings_is_immutable(self):
        cfg = default_config()
        custom = RecognizerSettings(name="foo", priority=1)
        cfg2 = cfg.with_recognizer_settings(custom)
        self.assertNotIn("foo", cfg.recognizer_settings)
        self.assertIn("foo", cfg2.recognizer_settings)

    def test_feature_toggles(self):
        cfg = default_config().with_feature_toggle("experimental_x", True)
        self.assertTrue(cfg.is_feature_enabled("experimental_x"))
        self.assertFalse(cfg.is_feature_enabled("unset_feature"))
        self.assertTrue(cfg.is_feature_enabled("unset_feature", default=True))


# ===========================================================================
# 4. Base: context / results / recognizer contract
# ===========================================================================

class TestRecognitionContext(unittest.TestCase):
    def test_minimal_construction(self):
        ctx = RecognitionContext(text="1. Introduction")
        self.assertEqual(ctx.text, "1. Introduction")
        self.assertIsNone(ctx.page)
        self.assertEqual(ctx.metadata, {})

    def test_is_frozen(self):
        ctx = _ctx()
        with self.assertRaises(Exception):
            ctx.text = "mutated"  # type: ignore[misc]

    def test_with_metadata_merges_without_mutating_original(self):
        ctx = RecognitionContext(text="x", metadata={"a": 1})
        ctx2 = ctx.with_metadata(b=2)
        self.assertEqual(ctx.metadata, {"a": 1})
        self.assertEqual(ctx2.metadata, {"a": 1, "b": 2})
        self.assertEqual(ctx2.text, "x")

    def test_metadata_defensively_copied(self):
        source = {"a": 1}
        ctx = RecognitionContext(text="x", metadata=source)
        source["a"] = 999
        self.assertEqual(ctx.metadata["a"], 1)


class TestRecognitionResult(unittest.TestCase):
    def test_valid_construction(self):
        result = RecognitionResult(
            recognizer_name="foo", classification=HeadingClassification.NUMBERED, confidence=0.8, level=2,
        )
        self.assertEqual(result.level, 2)
        self.assertEqual(result.diagnostics, ())

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            RecognitionResult(recognizer_name="", classification=HeadingClassification.NUMBERED, confidence=0.5)

    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            RecognitionResult(recognizer_name="foo", classification=HeadingClassification.NUMBERED, confidence=1.1)

    def test_level_below_one_rejected(self):
        with self.assertRaises(ValueError):
            RecognitionResult(
                recognizer_name="foo", classification=HeadingClassification.NUMBERED, confidence=0.5, level=0,
            )

    def test_is_frozen(self):
        result = RecognitionResult(recognizer_name="foo", classification=HeadingClassification.NUMBERED, confidence=0.5)
        with self.assertRaises(Exception):
            result.confidence = 0.9  # type: ignore[misc]


class TestFailureResult(unittest.TestCase):
    def test_requires_name_and_reason(self):
        with self.assertRaises(ValueError):
            FailureResult(recognizer_name="", reason="x")
        with self.assertRaises(ValueError):
            FailureResult(recognizer_name="foo", reason="")


class TestConfidenceInfo(unittest.TestCase):
    def test_valid(self):
        info = ConfidenceInfo(raw_confidence=0.6, adjusted_confidence=0.6, threshold=0.5, passed=True)
        self.assertTrue(info.passed)

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            ConfidenceInfo(raw_confidence=1.5, adjusted_confidence=0.5, threshold=0.5, passed=True)


class TestHeadingRecognizerContract(unittest.TestCase):
    def test_default_supports_is_true(self):
        recognizer = _AlwaysMatchRecognizer()
        self.assertTrue(recognizer.supports(_ctx()))

    def test_safe_recognize_returns_result_on_match(self):
        recognizer = _AlwaysMatchRecognizer()
        result = recognizer.safe_recognize(_ctx())
        self.assertIsInstance(result, RecognitionResult)

    def test_safe_recognize_returns_none_on_no_match(self):
        recognizer = _NeverMatchRecognizer()
        self.assertIsNone(recognizer.safe_recognize(_ctx()))

    def test_safe_recognize_wraps_exception(self):
        recognizer = _ExplodingRecognizer()
        with self.assertRaises(RecognizerExecutionError):
            recognizer.safe_recognize(_ctx())

    def test_cannot_instantiate_abstract_base(self):
        with self.assertRaises(TypeError):
            HeadingRecognizer()  # type: ignore[abstract]


# ===========================================================================
# 5. Registry
# ===========================================================================

class TestRecognizerRegistry(unittest.TestCase):
    def test_register_and_get(self):
        registry = RecognizerRegistry()
        recognizer = _AlwaysMatchRecognizer()
        registry.register(recognizer)
        self.assertIs(registry.get("always_match"), recognizer)
        self.assertIn("always_match", registry)
        self.assertEqual(len(registry), 1)

    def test_duplicate_registration_rejected(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        with self.assertRaises(RecognizerRegistrationError):
            registry.register(_AlwaysMatchRecognizer())

    def test_register_non_recognizer_rejected(self):
        registry = RecognizerRegistry()
        with self.assertRaises(RecognizerRegistrationError):
            registry.register(object())  # type: ignore[arg-type]

    def test_lookup_missing_raises(self):
        registry = RecognizerRegistry()
        with self.assertRaises(RecognizerLookupError):
            registry.get("nope")
        with self.assertRaises(RecognizerLookupError):
            registry.enable("nope")
        with self.assertRaises(RecognizerLookupError):
            registry.unregister("nope")

    def test_unregister_removes_completely(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        registry.unregister("always_match")
        self.assertNotIn("always_match", registry)
        self.assertEqual(registry.registered_names(), [])

    def test_new_registration_defaults_to_enabled(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        self.assertEqual(registry.state_of("always_match"), RecognizerState.ENABLED)
        self.assertTrue(registry.is_enabled("always_match"))

    def test_registration_honors_disabled_setting(self):
        cfg = default_config(recognizer_settings={
            "always_match": RecognizerSettings(name="always_match", enabled=False),
        })
        registry = RecognizerRegistry(config=cfg)
        registry.register(_AlwaysMatchRecognizer())
        self.assertEqual(registry.state_of("always_match"), RecognizerState.DISABLED)

    def test_enable_disable_lifecycle(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        registry.disable("always_match")
        self.assertFalse(registry.is_enabled("always_match"))
        registry.enable("always_match")
        self.assertTrue(registry.is_enabled("always_match"))

    def test_mark_failed_excludes_from_enabled(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        registry.mark_failed("always_match")
        self.assertEqual(registry.state_of("always_match"), RecognizerState.FAILED)
        self.assertFalse(registry.is_enabled("always_match"))
        self.assertIn("always_match", [r.name for r in registry.all_recognizers()])
        self.assertNotIn("always_match", [r.name for r in registry.enabled_recognizers()])

    def test_ordering_by_priority_then_registration_order(self):
        cfg = default_config(recognizer_settings={
            "low_priority": RecognizerSettings(name="low_priority", priority=200),
            "high_priority": RecognizerSettings(name="high_priority", priority=1),
        })
        registry = RecognizerRegistry(config=cfg)
        registry.register(_AlwaysMatchRecognizer(name="low_priority"))
        registry.register(_AlwaysMatchRecognizer(name="high_priority"))
        registry.register(_AlwaysMatchRecognizer(name="default_priority"))  # priority 100 default
        ordered = [r.name for r in registry.all_recognizers()]
        self.assertEqual(ordered, ["high_priority", "default_priority", "low_priority"])

    def test_ordering_tie_break_is_registration_order(self):
        registry = RecognizerRegistry()  # both default priority (100)
        registry.register(_AlwaysMatchRecognizer(name="first"))
        registry.register(_AlwaysMatchRecognizer(name="second"))
        ordered = [r.name for r in registry.all_recognizers()]
        self.assertEqual(ordered, ["first", "second"])

    def test_with_config_preserves_recognizers_new_registry(self):
        registry = RecognizerRegistry()
        recognizer = _AlwaysMatchRecognizer()
        registry.register(recognizer)
        new_cfg = default_config(recognizer_settings={
            "always_match": RecognizerSettings(name="always_match", enabled=False),
        })
        new_registry = registry.with_config(new_cfg)
        self.assertIsNot(new_registry, registry)
        self.assertTrue(registry.is_enabled("always_match"))
        self.assertFalse(new_registry.is_enabled("always_match"))
        self.assertIs(new_registry.get("always_match"), recognizer)


# ===========================================================================
# 6. Factory
# ===========================================================================

class TestRecognizerFactory(unittest.TestCase):
    def test_register_class_and_create(self):
        factory = RecognizerFactory()
        factory.register_class("always_match", _AlwaysMatchRecognizer)
        recognizer = factory.create("always_match")
        self.assertIsInstance(recognizer, _AlwaysMatchRecognizer)
        self.assertEqual(recognizer.name, "always_match")

    def test_create_unknown_name_raises(self):
        factory = RecognizerFactory()
        with self.assertRaises(RecognizerConfigurationError):
            factory.create("nope")

    def test_register_class_rejects_non_recognizer(self):
        factory = RecognizerFactory()
        with self.assertRaises(RecognizerConfigurationError):
            factory.register_class("bad", object)  # type: ignore[arg-type]

    def test_register_builder_function(self):
        factory = RecognizerFactory()

        def _build(settings):
            return _AlwaysMatchRecognizer(name="via_builder", confidence=0.42)

        factory.register_class("via_builder", _build)
        recognizer = factory.create("via_builder")
        self.assertEqual(recognizer.name, "via_builder")

    def test_name_mismatch_detected(self):
        factory = RecognizerFactory()

        def _build(settings):
            return _AlwaysMatchRecognizer(name="actual_name")

        factory.register_class("declared_name", _build)
        with self.assertRaises(RecognizerConfigurationError):
            factory.create("declared_name")

    def test_create_all(self):
        factory = RecognizerFactory()
        factory.register_class("a", lambda settings: _AlwaysMatchRecognizer(name="a"))
        factory.register_class("b", lambda settings: _NeverMatchRecognizer(name="b"))
        created = factory.create_all()
        self.assertEqual({r.name for r in created}, {"a", "b"})

    def test_build_registry(self):
        factory = RecognizerFactory()
        factory.register_class("a", lambda settings: _AlwaysMatchRecognizer(name="a"))
        registry = factory.build_registry()
        self.assertIn("a", registry)

    def test_with_config_preserves_builders(self):
        factory = RecognizerFactory()
        factory.register_class("a", lambda settings: _AlwaysMatchRecognizer(name="a"))
        new_factory = factory.with_config(default_config(global_confidence_threshold=0.9))
        self.assertIsNot(new_factory, factory)
        self.assertEqual(new_factory.registered_names(), ["a"])
        self.assertEqual(new_factory.config.global_confidence_threshold, 0.9)


# ===========================================================================
# 7. Pipeline
# ===========================================================================

class TestRecognitionPipelineOutcomes(unittest.TestCase):
    def test_matched_outcome(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer())
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.winner.recognizer_name, "always_match")

    def test_no_match_outcome(self):
        registry = RecognizerRegistry()
        registry.register(_NeverMatchRecognizer())
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        self.assertEqual(result.matches, ())
        self.assertIsNone(result.winner)
        self.assertEqual(result.attempts[0].outcome, RecognitionOutcome.NO_MATCH)

    def test_failed_outcome_recorded_without_aborting_pipeline(self):
        registry = RecognizerRegistry()
        registry.register(_ExplodingRecognizer(name="boom"))
        registry.register(_AlwaysMatchRecognizer(name="ok"))
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        failed = result.attempts_by_outcome(RecognitionOutcome.FAILED)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].recognizer_name, "boom")
        self.assertIsNotNone(failed[0].failure)
        # the exploding recognizer must not prevent the other from matching
        self.assertEqual(result.winner.recognizer_name, "ok")

    def test_skipped_outcome_when_unsupported(self):
        registry = RecognizerRegistry()
        registry.register(_UnsupportedRecognizer())
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        self.assertEqual(result.attempts[0].outcome, RecognitionOutcome.SKIPPED)

    def test_disabled_recognizer_is_not_invoked(self):
        registry = RecognizerRegistry()
        registry.register(_ExplodingRecognizer(name="boom"))
        registry.disable("boom")
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        self.assertEqual(result.attempts, ())  # never even attempted

    def test_below_threshold_match_counts_as_no_match(self):
        cfg = default_config(recognizer_settings={
            "always_match": RecognizerSettings(name="always_match", confidence_threshold=0.95),
        })
        registry = RecognizerRegistry(config=cfg)
        registry.register(_AlwaysMatchRecognizer(confidence=0.5))
        pipeline = RecognitionPipeline(registry, config=cfg)
        result = pipeline.run(_ctx())
        self.assertEqual(result.matches, ())
        attempt = result.attempts[0]
        self.assertEqual(attempt.outcome, RecognitionOutcome.NO_MATCH)
        self.assertIsNotNone(attempt.result)  # low-confidence result preserved for diagnostics

    def test_winner_raises_when_multiple_and_not_all_matches_strategy_not_hit(self):
        # sanity: with default (HIGHEST_CONFIDENCE) strategy there's always
        # exactly one winner when there's at least one match.
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer(name="a", confidence=0.6))
        registry.register(_AlwaysMatchRecognizer(name="b", confidence=0.9))
        pipeline = RecognitionPipeline(registry)
        result = pipeline.run(_ctx())
        self.assertEqual(len(result.winners), 1)
        self.assertEqual(result.winner.recognizer_name, "b")


class TestConflictResolutionStrategies(unittest.TestCase):
    def _registry(self) -> RecognizerRegistry:
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer(name="low_conf", confidence=0.5))
        registry.register(_AlwaysMatchRecognizer(name="high_conf", confidence=0.95))
        return registry

    def test_highest_confidence(self):
        cfg = default_config(conflict_resolution=ConflictResolutionStrategy.HIGHEST_CONFIDENCE)
        pipeline = RecognitionPipeline(self._registry(), config=cfg)
        result = pipeline.run(_ctx())
        self.assertEqual(result.winner.recognizer_name, "high_conf")

    def test_first_match(self):
        cfg = default_config(conflict_resolution=ConflictResolutionStrategy.FIRST_MATCH)
        pipeline = RecognitionPipeline(self._registry(), config=cfg)
        result = pipeline.run(_ctx())
        # registration order: low_conf registered first
        self.assertEqual(result.winner.recognizer_name, "low_conf")

    def test_priority_order(self):
        cfg = default_config(
            conflict_resolution=ConflictResolutionStrategy.PRIORITY_ORDER,
            recognizer_settings={
                "high_conf": RecognizerSettings(name="high_conf", priority=5),
                "low_conf": RecognizerSettings(name="low_conf", priority=50),
            },
        )
        pipeline = RecognitionPipeline(self._registry(), config=cfg)
        result = pipeline.run(_ctx())
        self.assertEqual(result.winner.recognizer_name, "high_conf")

    def test_all_matches(self):
        cfg = default_config(conflict_resolution=ConflictResolutionStrategy.ALL_MATCHES)
        pipeline = RecognitionPipeline(self._registry(), config=cfg)
        result = pipeline.run(_ctx())
        self.assertEqual(len(result.winners), 2)
        self.assertEqual(result.winners[0].recognizer_name, "high_conf")  # confidence-desc order
        with self.assertRaises(RecognitionPipelineError):
            _ = result.winner  # ambiguous with >1 winner

    def test_no_matches_returns_empty_winners_for_every_strategy(self):
        registry = RecognizerRegistry()
        registry.register(_NeverMatchRecognizer())
        for strategy in ConflictResolutionStrategy:
            cfg = default_config(conflict_resolution=strategy)
            pipeline = RecognitionPipeline(registry, config=cfg)
            result = pipeline.run(_ctx())
            self.assertEqual(result.winners, ())


class TestPipelineDeterminism(unittest.TestCase):
    def test_repeated_runs_are_identical(self):
        registry = RecognizerRegistry()
        registry.register(_AlwaysMatchRecognizer(name="a", confidence=0.7))
        registry.register(_AlwaysMatchRecognizer(name="b", confidence=0.7))  # tie on confidence
        pipeline = RecognitionPipeline(registry)
        first = pipeline.run(_ctx())
        second = pipeline.run(_ctx())
        self.assertEqual(
            [(a.recognizer_name, a.outcome) for a in first.attempts],
            [(a.recognizer_name, a.outcome) for a in second.attempts],
        )
        self.assertEqual(first.winner.recognizer_name, second.winner.recognizer_name)
        # tie-break is deterministic (registration order): "a" wins
        self.assertEqual(first.winner.recognizer_name, "a")


# ===========================================================================
# 8. Utils
# ===========================================================================

class TestRomanNumerals(unittest.TestCase):
    def test_round_trip(self):
        for value in (1, 4, 9, 14, 40, 90, 444, 1994, 3999):
            numeral = hr_utils.int_to_roman(value)
            self.assertIsNotNone(numeral)
            self.assertEqual(hr_utils.roman_to_int(numeral), value)

    def test_known_values(self):
        self.assertEqual(hr_utils.roman_to_int("XIV"), 14)
        self.assertEqual(hr_utils.roman_to_int("MCMXCIV"), 1994)
        self.assertEqual(hr_utils.int_to_roman(1994), "MCMXCIV")

    def test_case_insensitive(self):
        self.assertEqual(hr_utils.roman_to_int("xiv"), 14)

    def test_invalid_numeral_returns_none(self):
        self.assertIsNone(hr_utils.roman_to_int("IIII"))
        self.assertIsNone(hr_utils.roman_to_int("ABC"))
        self.assertIsNone(hr_utils.roman_to_int(""))

    def test_int_to_roman_out_of_range(self):
        self.assertIsNone(hr_utils.int_to_roman(0))
        self.assertIsNone(hr_utils.int_to_roman(4000))

    def test_is_roman_numeral(self):
        self.assertTrue(hr_utils.is_roman_numeral("IX"))
        self.assertFalse(hr_utils.is_roman_numeral("IIII"))
        self.assertFalse(hr_utils.is_roman_numeral(""))


class TestHierarchicalNumbering(unittest.TestCase):
    def test_parse_basic(self):
        self.assertEqual(hr_utils.parse_hierarchical_number("1.2.3"), ("1", "2", "3"))
        self.assertEqual(hr_utils.parse_hierarchical_number("2-1"), ("2", "1"))

    def test_single_segment_is_not_hierarchical(self):
        self.assertIsNone(hr_utils.parse_hierarchical_number("1"))

    def test_empty_segments_rejected(self):
        self.assertIsNone(hr_utils.parse_hierarchical_number("1..2"))
        self.assertIsNone(hr_utils.parse_hierarchical_number("1."))

    def test_depth(self):
        self.assertEqual(hr_utils.hierarchical_depth("1.2.3"), 3)
        self.assertIsNone(hr_utils.hierarchical_depth("1"))

    def test_compare_numeric(self):
        self.assertEqual(hr_utils.compare_hierarchical("1.2", "1.10"), -1)  # numeric, not lexicographic
        self.assertEqual(hr_utils.compare_hierarchical("1.2", "1.2"), 0)
        self.assertEqual(hr_utils.compare_hierarchical("1.3", "1.2"), 1)

    def test_compare_prefix_shorter_first(self):
        self.assertEqual(hr_utils.compare_hierarchical("1.2", "1.2.1"), -1)

    def test_compare_invalid_returns_none(self):
        self.assertIsNone(hr_utils.compare_hierarchical("1", "1.2"))


class TestAlphabeticMarkers(unittest.TestCase):
    def test_is_alphabetic_marker(self):
        self.assertTrue(hr_utils.is_alphabetic_marker("a)"))
        self.assertTrue(hr_utils.is_alphabetic_marker("(b)"))
        self.assertTrue(hr_utils.is_alphabetic_marker("C."))
        self.assertFalse(hr_utils.is_alphabetic_marker("ab)"))
        self.assertFalse(hr_utils.is_alphabetic_marker("1)"))

    def test_alphabetic_marker_to_index(self):
        self.assertEqual(hr_utils.alphabetic_marker_to_index("a)"), 1)
        self.assertEqual(hr_utils.alphabetic_marker_to_index("(c)"), 3)
        self.assertIsNone(hr_utils.alphabetic_marker_to_index("1)"))


class TestTextHelpers(unittest.TestCase):
    def test_strip_trailing_punctuation(self):
        self.assertEqual(hr_utils.strip_trailing_punctuation("Introduction :"), "Introduction")
        self.assertEqual(hr_utils.strip_trailing_punctuation("Chapter 1---"), "Chapter 1")
        self.assertEqual(hr_utils.strip_trailing_punctuation(""), "")

    def test_normalize_heading_whitespace(self):
        self.assertEqual(hr_utils.normalize_heading_whitespace("  Chapter   1  "), "Chapter 1")


class TestConfidenceHelpers(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(hr_utils.clamp_confidence(1.5), 1.0)
        self.assertEqual(hr_utils.clamp_confidence(-0.5), 0.0)
        self.assertEqual(hr_utils.clamp_confidence(0.42), 0.42)

    def test_combine_is_multiplicative(self):
        self.assertAlmostEqual(hr_utils.combine_confidence(0.5, 0.5), 0.25)
        self.assertEqual(hr_utils.combine_confidence(), 1.0)
        self.assertEqual(hr_utils.combine_confidence(0.9, base=0.5), 0.45)

    def test_meets_threshold(self):
        self.assertTrue(hr_utils.meets_threshold(0.6, 0.5))
        self.assertFalse(hr_utils.meets_threshold(0.4, 0.5))
        self.assertTrue(hr_utils.meets_threshold(0.5, 0.5))


if __name__ == "__main__":
    unittest.main()
