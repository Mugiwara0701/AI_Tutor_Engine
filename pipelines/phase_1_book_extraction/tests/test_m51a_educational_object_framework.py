"""
tests/test_m51a_educational_object_framework.py — M5.1 unit tests for
modules/educational_object_framework (the educational object
processing FRAMEWORK: no concrete processor is implemented in M5.1,
so these tests exercise the framework itself against small
test-double processors defined in this file).

Coverage:
  - enums: membership / string-value contracts
  - exceptions: hierarchy relationships
  - models: ProcessingResult validation, immutability, equality,
    with_updates()/with_diagnostic()/with_metadata()
  - validation: ValidationDiagnostic / ValidationResult status
    derivation, merged_with()
  - base: ProcessingContext immutability + with_metadata()/
    with_diagnostic()/with_current_object(), genericity (no hard-coded
    object type), ProcessingFailure validation,
    EducationalObjectProcessor safe_process() exception wrapping,
    supports() default
  - config: ProcessorSettings / EducationalObjectFrameworkConfig
    validation, immutability, settings_for() defaulting, with_* helpers
  - registry: registration, duplicate rejection, validation failures,
    lookup errors, enable/disable/mark_failed lifecycle, deterministic
    priority + registration-order ordering, with_config(),
    singleton default_registry
  - pipeline: EXECUTED / NO_RESULT / FAILED / SKIPPED outcomes,
    aggregate (not chained, not competing) execution — every processor
    sees the SAME context, deterministic output across repeated runs,
    graceful failure handling, never aborts on one processor's failure
  - public API: stable interfaces, deterministic behaviour
  - regression: modules.heading_recognizers / modules.heading_canonicalization
    remain importable and untouched by this package
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.educational_object_framework.base import (
    EducationalObjectProcessor,
    ProcessingContext,
    ProcessingFailure,
)
from modules.educational_object_framework.config import (
    EducationalObjectFrameworkConfig,
    ProcessorSettings,
    default_config,
)
from modules.educational_object_framework.enums import (
    DiagnosticSeverity,
    ProcessingOutcome,
    ProcessorState,
)
from modules.educational_object_framework.exceptions import (
    EducationalObjectFrameworkError,
    ProcessingPipelineError,
    ProcessingResultValidationError,
    ProcessorConfigurationError,
    ProcessorExecutionError,
    ProcessorLookupError,
    ProcessorRegistrationError,
)
from modules.educational_object_framework.models import ProcessingResult
from modules.educational_object_framework.pipeline import (
    AttemptRecord,
    ProcessingPipeline,
)
from modules.educational_object_framework.registry import ProcessorRegistry
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)


# ===========================================================================
# Test doubles — NOT concrete processors (those are out of M5.1's
# scope). Small, deterministic stand-ins used only to exercise the
# framework.
# ===========================================================================

class _AlwaysExecutesProcessor(EducationalObjectProcessor):
    """Always returns a ProcessingResult (EXECUTED)."""

    def __init__(self, name: str = "always_executes", value: str = "ok"):
        self.name = name
        self._value = value

    def process(self, context):
        return ProcessingResult(processor_name=self.name, metadata={"value": self._value})


class _NeverExecutesProcessor(EducationalObjectProcessor):
    """Always returns None (NO_RESULT)."""

    name = "never_executes"

    def process(self, context):
        return None


class _AlwaysRaisesProcessor(EducationalObjectProcessor):
    """Always raises inside process()."""

    name = "always_raises"

    def process(self, context):
        raise ValueError("boom")


class _UnsupportedProcessor(EducationalObjectProcessor):
    """supports() always returns False."""

    name = "unsupported"

    def supports(self, context):
        return False

    def process(self, context):  # pragma: no cover - never called
        raise AssertionError("process() should never be called when supports() is False")


class _SupportsRaisesProcessor(EducationalObjectProcessor):
    """supports() itself raises."""

    name = "supports_raises"

    def supports(self, context):
        raise RuntimeError("supports blew up")

    def process(self, context):  # pragma: no cover
        raise AssertionError("process() should never be called")


class _ObjectTypeGatedProcessor(EducationalObjectProcessor):
    """Only supports a specific context.object_type — used to prove
    the context is generic and processors, not the framework, decide
    what they apply to."""

    def __init__(self, name: str, object_type: str):
        self.name = name
        self._object_type = object_type

    def supports(self, context):
        return context.object_type == self._object_type

    def process(self, context):
        return ProcessingResult(processor_name=self.name, object_type=self._object_type)


class _RecordingProcessor(EducationalObjectProcessor):
    """Records the exact context it received — used to prove every
    processor sees the SAME (unmutated) context, unlike a cooperative
    canonicalization-style pipeline."""

    def __init__(self, name: str):
        self.name = name
        self.seen_contexts = []

    def process(self, context):
        self.seen_contexts.append(context)
        return ProcessingResult(processor_name=self.name)


# ===========================================================================
# enums
# ===========================================================================

class EnumsTest(unittest.TestCase):
    def test_processor_state_members(self):
        self.assertEqual(
            {s.value for s in ProcessorState},
            {"registered", "enabled", "disabled", "failed"},
        )

    def test_processing_outcome_members(self):
        self.assertEqual(
            {o.value for o in ProcessingOutcome},
            {"executed", "no_result", "failed", "skipped"},
        )

    def test_diagnostic_severity_members(self):
        self.assertEqual(
            {s.value for s in DiagnosticSeverity},
            {"info", "warning", "error"},
        )

    def test_string_backed_equality(self):
        self.assertEqual(ProcessorState.ENABLED, "enabled")
        self.assertEqual(ProcessingOutcome.EXECUTED, "executed")
        self.assertEqual(DiagnosticSeverity.ERROR, "error")

    def test_no_object_specific_enum_members(self):
        """M5.1 spec: the framework must not hard-code any educational
        object type. None of the shared vocabularies may name a
        specific object kind."""
        forbidden = {"equation", "figure", "table", "diagram", "example", "activity", "definition", "glossary"}
        all_values = (
            {s.value for s in ProcessorState}
            | {o.value for o in ProcessingOutcome}
            | {s.value for s in DiagnosticSeverity}
        )
        self.assertEqual(all_values & forbidden, set())


# ===========================================================================
# exceptions
# ===========================================================================

class ExceptionsTest(unittest.TestCase):
    def test_hierarchy(self):
        for cls in (
            ProcessorRegistrationError,
            ProcessorConfigurationError,
            ProcessorLookupError,
            ProcessorExecutionError,
            ProcessingPipelineError,
            ProcessingResultValidationError,
        ):
            self.assertTrue(issubclass(cls, EducationalObjectFrameworkError))

    def test_lookup_error_is_also_lookup_error(self):
        self.assertTrue(issubclass(ProcessorLookupError, LookupError))

    def test_execution_error_message(self):
        exc = ProcessorExecutionError("my_processor", "kaboom")
        self.assertIn("my_processor", str(exc))
        self.assertIn("kaboom", str(exc))
        self.assertEqual(exc.processor_name, "my_processor")


# ===========================================================================
# models — ProcessingResult
# ===========================================================================

class ProcessingResultTest(unittest.TestCase):
    def test_construction_defaults(self):
        result = ProcessingResult(processor_name="p")
        self.assertEqual(result.processor_name, "p")
        self.assertTrue(result.success)
        self.assertIsNone(result.object_type)
        self.assertEqual(result.diagnostics, ())
        self.assertEqual(result.metadata, {})
        self.assertEqual(result.execution_metadata, {})

    def test_immutability(self):
        result = ProcessingResult(processor_name="p")
        with self.assertRaises(Exception):
            result.processor_name = "changed"  # type: ignore[misc]

    def test_empty_processor_name_rejected(self):
        with self.assertRaises(ProcessingResultValidationError):
            ProcessingResult(processor_name="")
        with self.assertRaises(ProcessingResultValidationError):
            ProcessingResult(processor_name="   ")

    def test_diagnostics_and_metadata_are_defensively_copied(self):
        diagnostics = ["a"]
        metadata = {"k": "v"}
        result = ProcessingResult(processor_name="p", diagnostics=diagnostics, metadata=metadata)
        diagnostics.append("b")
        metadata["k2"] = "v2"
        self.assertEqual(result.diagnostics, ("a",))
        self.assertEqual(result.metadata, {"k": "v"})

    def test_with_updates(self):
        result = ProcessingResult(processor_name="p")
        updated = result.with_updates(success=False)
        self.assertTrue(result.success)
        self.assertFalse(updated.success)
        self.assertIsNot(result, updated)

    def test_with_diagnostic(self):
        result = ProcessingResult(processor_name="p").with_diagnostic("note 1").with_diagnostic("note 2")
        self.assertEqual(result.diagnostics, ("note 1", "note 2"))

    def test_with_metadata_merges(self):
        result = ProcessingResult(processor_name="p", metadata={"a": 1})
        updated = result.with_metadata(b=2)
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertEqual(result.metadata, {"a": 1})

    def test_equality(self):
        self.assertEqual(ProcessingResult(processor_name="p"), ProcessingResult(processor_name="p"))
        self.assertNotEqual(ProcessingResult(processor_name="p"), ProcessingResult(processor_name="q"))


# ===========================================================================
# validation
# ===========================================================================

class ValidationTest(unittest.TestCase):
    def test_success_constant_has_no_diagnostics(self):
        self.assertEqual(SUCCESS.diagnostics, ())
        self.assertTrue(SUCCESS.is_success)
        self.assertFalse(SUCCESS.has_errors)
        self.assertFalse(SUCCESS.has_warnings)

    def test_diagnostic_requires_non_empty_code_and_message(self):
        with self.assertRaises(ValueError):
            ValidationDiagnostic(severity=DiagnosticSeverity.INFO, code="", message="m")
        with self.assertRaises(ValueError):
            ValidationDiagnostic(severity=DiagnosticSeverity.INFO, code="c", message="")

    def test_status_derivation(self):
        info_only = ValidationResult(diagnostics=(
            ValidationDiagnostic(severity=DiagnosticSeverity.INFO, code="c1", message="m1"),
        ))
        self.assertTrue(info_only.is_success)

        with_warning = ValidationResult(diagnostics=(
            ValidationDiagnostic(severity=DiagnosticSeverity.WARNING, code="c2", message="m2"),
        ))
        self.assertTrue(with_warning.is_success)
        self.assertTrue(with_warning.has_warnings)

        with_error = ValidationResult(diagnostics=(
            ValidationDiagnostic(severity=DiagnosticSeverity.ERROR, code="c3", message="m3"),
        ))
        self.assertFalse(with_error.is_success)
        self.assertTrue(with_error.has_errors)

    def test_merged_with_preserves_order(self):
        d1 = ValidationDiagnostic(severity=DiagnosticSeverity.INFO, code="c1", message="m1")
        d2 = ValidationDiagnostic(severity=DiagnosticSeverity.WARNING, code="c2", message="m2")
        merged = ValidationResult(diagnostics=(d1,)).merged_with(ValidationResult(diagnostics=(d2,)))
        self.assertEqual(merged.diagnostics, (d1, d2))

    def test_errors_and_warnings_filters(self):
        d1 = ValidationDiagnostic(severity=DiagnosticSeverity.ERROR, code="c1", message="m1")
        d2 = ValidationDiagnostic(severity=DiagnosticSeverity.WARNING, code="c2", message="m2")
        result = ValidationResult(diagnostics=(d1, d2))
        self.assertEqual(result.errors(), (d1,))
        self.assertEqual(result.warnings(), (d2,))


# ===========================================================================
# base — ProcessingContext, ProcessingFailure, EducationalObjectProcessor
# ===========================================================================

class ProcessingContextTest(unittest.TestCase):
    def test_defaults(self):
        context = ProcessingContext()
        self.assertIsNone(context.current_object)
        self.assertIsNone(context.object_type)
        self.assertEqual(context.chapter_metadata, {})
        self.assertEqual(context.surrounding_context, {})
        self.assertIsNone(context.book_id)
        self.assertIsNone(context.chapter_id)
        self.assertEqual(context.metadata, {})
        self.assertEqual(context.diagnostics, ())

    def test_current_object_accepts_any_shape(self):
        """M5.1 spec: the context must be generic and must not hard-
        code any educational object type — it should accept whatever
        an upstream stage puts there."""
        for candidate in (None, "raw text", {"kind": "equation"}, 42, object()):
            context = ProcessingContext(current_object=candidate)
            self.assertIs(context.current_object, candidate)

    def test_immutability(self):
        context = ProcessingContext()
        with self.assertRaises(Exception):
            context.current_object = "changed"  # type: ignore[misc]

    def test_metadata_is_defensively_copied(self):
        metadata = {"a": 1}
        context = ProcessingContext(metadata=metadata)
        metadata["b"] = 2
        self.assertEqual(context.metadata, {"a": 1})

    def test_with_metadata_merges_without_mutating_original(self):
        context = ProcessingContext(metadata={"a": 1})
        updated = context.with_metadata(b=2)
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertEqual(context.metadata, {"a": 1})
        self.assertIsNot(context, updated)

    def test_with_diagnostic_appends(self):
        context = ProcessingContext().with_diagnostic("note 1").with_diagnostic("note 2")
        self.assertEqual(context.diagnostics, ("note 1", "note 2"))

    def test_with_current_object_replaces_object_and_type_only(self):
        context = ProcessingContext(
            current_object="old",
            object_type="old_type",
            book_id="book-1",
            chapter_metadata={"chapter_number": 3},
        )
        updated = context.with_current_object("new", object_type="new_type")
        self.assertEqual(updated.current_object, "new")
        self.assertEqual(updated.object_type, "new_type")
        self.assertEqual(updated.book_id, "book-1")
        self.assertEqual(updated.chapter_metadata, {"chapter_number": 3})
        # original untouched
        self.assertEqual(context.current_object, "old")
        self.assertEqual(context.object_type, "old_type")

    def test_with_current_object_without_type_keeps_existing_type(self):
        context = ProcessingContext(current_object="old", object_type="kept")
        updated = context.with_current_object("new")
        self.assertEqual(updated.current_object, "new")
        self.assertEqual(updated.object_type, "kept")


class ProcessingFailureTest(unittest.TestCase):
    def test_requires_non_empty_processor_name_and_reason(self):
        with self.assertRaises(ValueError):
            ProcessingFailure(processor_name="", reason="r")
        with self.assertRaises(ValueError):
            ProcessingFailure(processor_name="p", reason="")

    def test_diagnostics_defaults_to_empty_tuple(self):
        failure = ProcessingFailure(processor_name="p", reason="r")
        self.assertEqual(failure.diagnostics, ())


class EducationalObjectProcessorTest(unittest.TestCase):
    def test_supports_defaults_true(self):
        processor = _AlwaysExecutesProcessor()
        self.assertTrue(processor.supports(ProcessingContext()))

    def test_safe_process_returns_result(self):
        processor = _AlwaysExecutesProcessor()
        result = processor.safe_process(ProcessingContext())
        self.assertIsInstance(result, ProcessingResult)

    def test_safe_process_wraps_exception(self):
        processor = _AlwaysRaisesProcessor()
        with self.assertRaises(ProcessorExecutionError) as ctx:
            processor.safe_process(ProcessingContext())
        self.assertEqual(ctx.exception.processor_name, "always_raises")
        self.assertIsInstance(ctx.exception.__cause__, ValueError)


# ===========================================================================
# config
# ===========================================================================

class ConfigTest(unittest.TestCase):
    def test_processor_settings_defaults(self):
        settings = ProcessorSettings(name="p")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.priority, 100)
        self.assertEqual(settings.extra, {})

    def test_processor_settings_requires_name(self):
        with self.assertRaises(ProcessorConfigurationError):
            ProcessorSettings(name="")

    def test_processor_settings_priority_must_be_int(self):
        with self.assertRaises(ProcessorConfigurationError):
            ProcessorSettings(name="p", priority="high")  # type: ignore[arg-type]
        with self.assertRaises(ProcessorConfigurationError):
            ProcessorSettings(name="p", priority=True)  # bool is not an int here

    def test_with_overrides(self):
        settings = ProcessorSettings(name="p", priority=10)
        updated = settings.with_overrides(priority=20)
        self.assertEqual(settings.priority, 10)
        self.assertEqual(updated.priority, 20)

    def test_settings_for_returns_default_when_unconfigured(self):
        config = default_config()
        settings = config.settings_for("unregistered_processor")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.priority, 100)

    def test_settings_for_returns_configured_override(self):
        config = default_config({"p": ProcessorSettings(name="p", enabled=False, priority=5)})
        settings = config.settings_for("p")
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.priority, 5)

    def test_with_processor_settings_returns_new_config(self):
        config = default_config()
        updated = config.with_processor_settings(ProcessorSettings(name="p", priority=1))
        self.assertEqual(config.settings_for("p").priority, 100)
        self.assertEqual(updated.settings_for("p").priority, 1)

    def test_feature_toggle(self):
        config = default_config()
        self.assertFalse(config.is_feature_enabled("some_feature"))
        updated = config.with_feature_toggle("some_feature", True)
        self.assertTrue(updated.is_feature_enabled("some_feature"))
        self.assertFalse(config.is_feature_enabled("some_feature"))


# ===========================================================================
# registry
# ===========================================================================

class ProcessorRegistryTest(unittest.TestCase):
    def test_register_and_get(self):
        registry = ProcessorRegistry()
        processor = _AlwaysExecutesProcessor()
        registry.register(processor)
        self.assertIs(registry.get("always_executes"), processor)
        self.assertIn("always_executes", registry)
        self.assertEqual(len(registry), 1)

    def test_register_duplicate_name_rejected(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="dup"))
        with self.assertRaises(ProcessorRegistrationError):
            registry.register(_AlwaysExecutesProcessor(name="dup"))

    def test_register_rejects_non_processor(self):
        registry = ProcessorRegistry()
        with self.assertRaises(ProcessorRegistrationError):
            registry.register(object())  # type: ignore[arg-type]

    def test_register_rejects_missing_name(self):
        class _NoName(EducationalObjectProcessor):
            name = ""

            def process(self, context):
                return None

        registry = ProcessorRegistry()
        with self.assertRaises(ProcessorRegistrationError):
            registry.register(_NoName())

    def test_unregister(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="p"))
        registry.unregister("p")
        self.assertNotIn("p", registry)
        with self.assertRaises(ProcessorLookupError):
            registry.get("p")

    def test_unregister_unknown_raises(self):
        registry = ProcessorRegistry()
        with self.assertRaises(ProcessorLookupError):
            registry.unregister("nope")

    def test_lifecycle_enable_disable_mark_failed(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="p"))
        self.assertTrue(registry.is_enabled("p"))
        registry.disable("p")
        self.assertFalse(registry.is_enabled("p"))
        self.assertEqual(registry.state_of("p"), ProcessorState.DISABLED)
        registry.enable("p")
        self.assertTrue(registry.is_enabled("p"))
        registry.mark_failed("p")
        self.assertEqual(registry.state_of("p"), ProcessorState.FAILED)
        self.assertFalse(registry.is_enabled("p"))

    def test_disabled_processor_registered_via_config(self):
        config = default_config({"p": ProcessorSettings(name="p", enabled=False)})
        registry = ProcessorRegistry(config=config)
        registry.register(_AlwaysExecutesProcessor(name="p"))
        self.assertFalse(registry.is_enabled("p"))
        self.assertIn("p", registry.registered_names())

    def test_deterministic_priority_ordering(self):
        config = default_config({
            "low": ProcessorSettings(name="low", priority=10),
            "high": ProcessorSettings(name="high", priority=200),
        })
        registry = ProcessorRegistry(config=config)
        registry.register(_AlwaysExecutesProcessor(name="high"))
        registry.register(_AlwaysExecutesProcessor(name="low"))
        ordered = [p.name for p in registry.all_processors()]
        self.assertEqual(ordered, ["low", "high"])

    def test_registration_order_breaks_priority_ties(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="first"))
        registry.register(_AlwaysExecutesProcessor(name="second"))
        registry.register(_AlwaysExecutesProcessor(name="third"))
        ordered = [p.name for p in registry.all_processors()]
        self.assertEqual(ordered, ["first", "second", "third"])

    def test_enabled_processors_excludes_disabled(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="a"))
        registry.register(_AlwaysExecutesProcessor(name="b"))
        registry.disable("b")
        self.assertEqual([p.name for p in registry.enabled_processors()], ["a"])

    def test_with_config_preserves_registration_but_rederives_state(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="a"))
        registry.register(_AlwaysExecutesProcessor(name="b"))
        new_config = default_config({"b": ProcessorSettings(name="b", enabled=False)})
        new_registry = registry.with_config(new_config)
        self.assertEqual(new_registry.registered_names(), ["a", "b"])
        self.assertTrue(new_registry.is_enabled("a"))
        self.assertFalse(new_registry.is_enabled("b"))
        # original untouched
        self.assertTrue(registry.is_enabled("b"))

    def test_default_registry_is_singleton_across_imports(self):
        from modules.educational_object_framework.registry import default_registry as r1
        from modules.educational_object_framework import default_registry as r2
        self.assertIs(r1, r2)


# ===========================================================================
# pipeline
# ===========================================================================

class ProcessingPipelineTest(unittest.TestCase):
    def test_executed_outcome(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor())
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        self.assertEqual(len(outcome.attempts), 1)
        self.assertEqual(outcome.attempts[0].outcome, ProcessingOutcome.EXECUTED)
        self.assertEqual(len(outcome.results), 1)
        self.assertEqual(outcome.results[0].processor_name, "always_executes")

    def test_no_result_outcome(self):
        registry = ProcessorRegistry()
        registry.register(_NeverExecutesProcessor())
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        self.assertEqual(outcome.attempts[0].outcome, ProcessingOutcome.NO_RESULT)
        self.assertEqual(outcome.results, ())

    def test_failed_outcome_does_not_abort_run(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysRaisesProcessor())
        registry.register(_AlwaysExecutesProcessor(name="after_failure"))
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        outcomes = {a.processor_name: a.outcome for a in outcome.attempts}
        self.assertEqual(outcomes["always_raises"], ProcessingOutcome.FAILED)
        self.assertEqual(outcomes["after_failure"], ProcessingOutcome.EXECUTED)
        self.assertEqual(len(outcome.failures), 1)
        self.assertEqual(outcome.failures[0].processor_name, "always_raises")

    def test_skipped_outcome_for_unsupported(self):
        registry = ProcessorRegistry()
        registry.register(_UnsupportedProcessor())
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        self.assertEqual(outcome.attempts[0].outcome, ProcessingOutcome.SKIPPED)

    def test_supports_raising_recorded_as_failed_not_aborted(self):
        registry = ProcessorRegistry()
        registry.register(_SupportsRaisesProcessor())
        registry.register(_AlwaysExecutesProcessor(name="after"))
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        outcomes = {a.processor_name: a.outcome for a in outcome.attempts}
        self.assertEqual(outcomes["supports_raises"], ProcessingOutcome.FAILED)
        self.assertEqual(outcomes["after"], ProcessingOutcome.EXECUTED)

    def test_every_processor_sees_the_same_context_aggregate_not_chained(self):
        """The defining structural difference from CanonicalizationPipeline:
        processors coexist against one shared context rather than
        cooperating on an evolving payload."""
        recorder_a = _RecordingProcessor("a")
        recorder_b = _RecordingProcessor("b")
        registry = ProcessorRegistry()
        registry.register(recorder_a)
        registry.register(recorder_b)
        pipeline = ProcessingPipeline(registry)
        context = ProcessingContext(current_object="fixed", metadata={"k": "v"})
        pipeline.run(context)
        self.assertIs(recorder_a.seen_contexts[0], context)
        self.assertIs(recorder_b.seen_contexts[0], context)

    def test_object_type_gating_lets_processors_coexist_without_conflict(self):
        registry = ProcessorRegistry()
        registry.register(_ObjectTypeGatedProcessor("eq_proc", "equation"))
        registry.register(_ObjectTypeGatedProcessor("fig_proc", "figure"))
        pipeline = ProcessingPipeline(registry)

        outcome = pipeline.run(ProcessingContext(object_type="equation"))
        self.assertEqual(outcome.executed_processor_names, ("eq_proc",))

        outcome2 = pipeline.run(ProcessingContext(object_type="figure"))
        self.assertEqual(outcome2.executed_processor_names, ("fig_proc",))

    def test_disabled_processor_is_never_invoked(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="p"))
        registry.disable("p")
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        self.assertEqual(outcome.attempts, ())

    def test_deterministic_across_repeated_runs(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor(name="p1"))
        registry.register(_NeverExecutesProcessor())
        registry.register(_AlwaysExecutesProcessor(name="p2"))
        pipeline = ProcessingPipeline(registry)
        context = ProcessingContext(current_object="x")

        run1 = pipeline.run(context)
        run2 = pipeline.run(context)
        self.assertEqual(
            [(a.processor_name, a.outcome) for a in run1.attempts],
            [(a.processor_name, a.outcome) for a in run2.attempts],
        )

    def test_successful_results_filters_domain_level_failures(self):
        class _DomainFailureProcessor(EducationalObjectProcessor):
            name = "domain_failure"

            def process(self, context):
                return ProcessingResult(processor_name=self.name, success=False)

        registry = ProcessorRegistry()
        registry.register(_DomainFailureProcessor())
        registry.register(_AlwaysExecutesProcessor(name="ok"))
        pipeline = ProcessingPipeline(registry)
        outcome = pipeline.run(ProcessingContext())
        self.assertEqual(len(outcome.results), 2)
        self.assertEqual(len(outcome.successful_results), 1)
        self.assertEqual(outcome.successful_results[0].processor_name, "ok")

    def test_pipeline_reusable_across_runs(self):
        registry = ProcessorRegistry()
        registry.register(_AlwaysExecutesProcessor())
        pipeline = ProcessingPipeline(registry)
        outcome1 = pipeline.run(ProcessingContext(current_object="a"))
        outcome2 = pipeline.run(ProcessingContext(current_object="b"))
        self.assertEqual(len(outcome1.attempts), 1)
        self.assertEqual(len(outcome2.attempts), 1)

    def test_attempt_record_requires_result_for_executed(self):
        with self.assertRaises(ValueError):
            AttemptRecord("p", ProcessingOutcome.EXECUTED, result=None)

    def test_attempt_record_requires_failure_for_failed(self):
        with self.assertRaises(ValueError):
            AttemptRecord("p", ProcessingOutcome.FAILED, failure=None)


# ===========================================================================
# public API
# ===========================================================================

class PublicApiTest(unittest.TestCase):
    def test_exports_present(self):
        import modules.educational_object_framework as pkg
        for name in pkg.__all__:
            self.assertTrue(hasattr(pkg, name), f"missing export: {name}")

    def test_register_convenience_function_uses_default_registry(self):
        import modules.educational_object_framework as pkg

        marker_name = "public_api_test_processor"
        if marker_name in pkg.default_registry:
            pkg.default_registry.unregister(marker_name)
        try:
            pkg.register(_AlwaysExecutesProcessor(name=marker_name))
            self.assertIn(marker_name, pkg.default_registry)
            self.assertIs(pkg.get(marker_name).name, marker_name)
        finally:
            pkg.default_registry.unregister(marker_name)


# ===========================================================================
# regression — the frozen M4 heading subsystem is untouched
# ===========================================================================

class RegressionTest(unittest.TestCase):
    def test_heading_recognizers_still_importable(self):
        import modules.heading_recognizers as hr
        self.assertTrue(hasattr(hr, "HeadingRecognizer"))

    def test_heading_canonicalization_still_importable(self):
        import modules.heading_canonicalization as hc
        self.assertTrue(hasattr(hc, "HeadingCanonicalizer"))

    def test_no_cross_package_import_dependency(self):
        """M5.1 spec: this package must not modify or depend on the
        frozen heading subsystem. Docstrings may mention the sibling
        packages for architectural context; no module may actually
        import from them."""
        import modules.educational_object_framework as pkg
        pkg_dir = Path(pkg.__file__).resolve().parent
        for py_file in pkg_dir.glob("*.py"):
            for line in py_file.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("from modules.heading_") or stripped.startswith("import modules.heading_"):
                    self.fail(f"{py_file.name} imports from the frozen heading subsystem: {stripped!r}")


if __name__ == "__main__":
    unittest.main()
