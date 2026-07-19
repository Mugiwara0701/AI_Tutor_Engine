"""
tests/test_m43a_heading_canonicalization_framework.py — M4.3A unit
tests for modules/heading_canonicalization (the heading
canonicalization FRAMEWORK: no concrete canonicalizer is implemented
in M4.3A, so these tests exercise the framework itself against small
test-double canonicalizers defined in this file).

Coverage:
  - enums: membership / string-value contracts
  - exceptions: hierarchy relationships
  - models: CanonicalHeading validation, immutability, equality,
    with_updates()/with_diagnostic()/with_metadata(), is_canonicalized,
    from_recognition() (M4.2 -> M4.3 adapter / backwards compatibility)
  - validation: ValidationDiagnostic / ValidationResult status
    derivation, merged_with()
  - base: CanonicalizationContext immutability + with_metadata(),
    CanonicalizationFailure validation, HeadingCanonicalizer
    safe_canonicalize() exception wrapping, supports() default
  - config: CanonicalizerSettings / HeadingCanonicalizationConfig
    validation, immutability, settings_for() defaulting, with_* helpers
  - registry: registration, duplicate rejection, validation failures,
    lookup errors, enable/disable/mark_failed lifecycle, deterministic
    priority + registration-order ordering, with_config()
  - pipeline: APPLIED / UNCHANGED / FAILED / SKIPPED outcomes,
    cooperative (not competing) heading threading, deterministic
    output across repeated runs, graceful failure handling
  - public API: stable interfaces, deterministic behaviour,
    backwards compatibility with M4.2 outputs
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules.heading_canonicalization.base import (
    CanonicalizationContext,
    CanonicalizationFailure,
    HeadingCanonicalizer,
)
from modules.heading_canonicalization.config import (
    CanonicalizerSettings,
    HeadingCanonicalizationConfig,
    default_config,
)
from modules.heading_canonicalization.enums import (
    CanonicalHeadingType,
    CanonicalizationOutcome,
    CanonicalizerState,
    NumberingSystem,
    ValidationSeverity,
    ValidationStatus,
)
from modules.heading_canonicalization.exceptions import (
    CanonicalHeadingValidationError,
    CanonicalizationPipelineError,
    CanonicalizerConfigurationError,
    CanonicalizerExecutionError,
    CanonicalizerLookupError,
    CanonicalizerRegistrationError,
    HeadingCanonicalizationError,
)
from modules.heading_canonicalization.models import CanonicalHeading
from modules.heading_canonicalization.pipeline import (
    AttemptRecord,
    CanonicalizationPipeline,
)
from modules.heading_canonicalization.registry import CanonicalizerRegistry
from modules.heading_canonicalization.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

from modules.heading_recognizers.base import RecognitionContext, RecognitionResult
from modules.heading_recognizers.enums import HeadingClassification


# ===========================================================================
# Test doubles — NOT concrete canonicalizers (those are out of M4.3A's
# scope). Small, deterministic stand-ins used only to exercise the
# framework.
# ===========================================================================

def _make_heading(**overrides) -> CanonicalHeading:
    defaults = dict(
        original_text="1.1",
        recognized_classification=HeadingClassification.NUMBERED,
        recognized_confidence=0.9,
        level=2,
        original_numbering="1.1",
        original_language="en",
    )
    defaults.update(overrides)
    return CanonicalHeading(**defaults)


class _AlwaysAppliesCanonicalizer(HeadingCanonicalizer):
    """Always returns an updated heading (sets canonical_number)."""

    def __init__(self, name: str = "always_applies", value: str = "1.1"):
        self.name = name
        self._value = value

    def canonicalize(self, heading, context):
        return heading.with_updates(canonical_number=self._value)


class _NeverAppliesCanonicalizer(HeadingCanonicalizer):
    """Always returns None (UNCHANGED)."""

    name = "never_applies"

    def canonicalize(self, heading, context):
        return None


class _AlwaysRaisesCanonicalizer(HeadingCanonicalizer):
    """Always raises inside canonicalize()."""

    name = "always_raises"

    def canonicalize(self, heading, context):
        raise ValueError("boom")


class _UnsupportedCanonicalizer(HeadingCanonicalizer):
    """supports() always returns False."""

    name = "unsupported"

    def supports(self, heading, context):
        return False

    def canonicalize(self, heading, context):  # pragma: no cover - never called
        raise AssertionError("canonicalize() should never be called when supports() is False")


class _SupportsRaisesCanonicalizer(HeadingCanonicalizer):
    """supports() itself raises."""

    name = "supports_raises"

    def supports(self, heading, context):
        raise RuntimeError("supports blew up")

    def canonicalize(self, heading, context):  # pragma: no cover
        raise AssertionError("canonicalize() should never be called")


class _AppendDiagnosticCanonicalizer(HeadingCanonicalizer):
    """Appends a diagnostic every time it runs — used to prove that
    two canonicalizers COOPERATE (each sees the previous one's
    output), unlike RecognitionPipeline's competing recognizers."""

    def __init__(self, name: str, message: str):
        self.name = name
        self._message = message

    def canonicalize(self, heading, context):
        return heading.with_diagnostic(self._message)


# ===========================================================================
# enums
# ===========================================================================

class EnumsTest(unittest.TestCase):
    def test_canonical_heading_type_members(self):
        self.assertEqual(CanonicalHeadingType.CHAPTER.value, "chapter")
        self.assertEqual(CanonicalHeadingType.SECTION.value, "section")
        self.assertEqual(CanonicalHeadingType.SUBSECTION.value, "subsection")
        self.assertEqual(CanonicalHeadingType.SUBSUBSECTION.value, "subsubsection")
        self.assertEqual(CanonicalHeadingType.KEYWORD_SECTION.value, "keyword_section")
        self.assertEqual(CanonicalHeadingType.UNSPECIFIED.value, "unspecified")

    def test_numbering_system_members(self):
        self.assertEqual(NumberingSystem.ARABIC.value, "arabic")
        self.assertEqual(NumberingSystem.ROMAN.value, "roman")
        self.assertEqual(NumberingSystem.DEVANAGARI.value, "devanagari")
        self.assertEqual(NumberingSystem.ALPHABETIC.value, "alphabetic")
        self.assertEqual(NumberingSystem.HIERARCHICAL.value, "hierarchical")
        self.assertEqual(NumberingSystem.NONE.value, "none")
        self.assertEqual(NumberingSystem.UNKNOWN.value, "unknown")

    def test_validation_status_members(self):
        self.assertEqual(ValidationStatus.PENDING.value, "pending")
        self.assertEqual(ValidationStatus.SUCCESS.value, "success")
        self.assertEqual(ValidationStatus.WARNING.value, "warning")
        self.assertEqual(ValidationStatus.ERROR.value, "error")

    def test_string_backed_equality(self):
        self.assertEqual(CanonicalHeadingType.CHAPTER, "chapter")
        self.assertEqual(NumberingSystem.ROMAN, "roman")

    def test_canonicalization_outcome_members(self):
        self.assertEqual(
            {o.value for o in CanonicalizationOutcome},
            {"applied", "unchanged", "failed", "skipped"},
        )

    def test_canonicalizer_state_members(self):
        self.assertEqual(
            {s.value for s in CanonicalizerState},
            {"registered", "enabled", "disabled", "failed"},
        )


# ===========================================================================
# exceptions
# ===========================================================================

class ExceptionsTest(unittest.TestCase):
    def test_hierarchy(self):
        for cls in (
            CanonicalizerRegistrationError,
            CanonicalizerConfigurationError,
            CanonicalizerLookupError,
            CanonicalizerExecutionError,
            CanonicalizationPipelineError,
            CanonicalHeadingValidationError,
        ):
            self.assertTrue(issubclass(cls, HeadingCanonicalizationError))

    def test_lookup_error_is_also_lookup_error(self):
        self.assertTrue(issubclass(CanonicalizerLookupError, LookupError))

    def test_execution_error_message(self):
        exc = CanonicalizerExecutionError("my_canonicalizer", "kaboom")
        self.assertIn("my_canonicalizer", str(exc))
        self.assertIn("kaboom", str(exc))
        self.assertEqual(exc.canonicalizer_name, "my_canonicalizer")


# ===========================================================================
# models — CanonicalHeading
# ===========================================================================

class CanonicalHeadingTest(unittest.TestCase):
    def test_construction_defaults(self):
        heading = _make_heading()
        self.assertEqual(heading.original_text, "1.1")
        self.assertIsNone(heading.canonical_type)
        self.assertIsNone(heading.canonical_number)
        self.assertEqual(heading.numbering_system, NumberingSystem.UNKNOWN)
        self.assertIsNone(heading.normalized_title)
        self.assertEqual(heading.validation_status, ValidationStatus.PENDING)
        self.assertEqual(heading.diagnostics, ())
        self.assertEqual(heading.metadata, {})

    def test_immutability(self):
        heading = _make_heading()
        with self.assertRaises(Exception):
            heading.original_text = "changed"  # type: ignore[misc]

    def test_equality(self):
        a = _make_heading()
        b = _make_heading()
        self.assertEqual(a, b)
        c = _make_heading(original_text="different")
        self.assertNotEqual(a, c)

    def test_empty_text_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(original_text="   ")

    def test_bad_classification_type_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(recognized_classification="numbered")  # not an enum member

    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(recognized_confidence=1.5)

    def test_negative_level_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(level=0)

    def test_bad_canonical_type_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(canonical_type="chapter")  # not an enum member

    def test_bad_numbering_system_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(numbering_system="arabic")  # not an enum member

    def test_bad_validation_status_rejected(self):
        with self.assertRaises(CanonicalHeadingValidationError):
            _make_heading(validation_status="success")  # not an enum member

    def test_with_updates_returns_new_instance(self):
        heading = _make_heading()
        updated = heading.with_updates(canonical_number="1")
        self.assertIsNot(heading, updated)
        self.assertIsNone(heading.canonical_number)
        self.assertEqual(updated.canonical_number, "1")
        # every other field copied unchanged
        self.assertEqual(updated.original_text, heading.original_text)

    def test_with_diagnostic_appends(self):
        heading = _make_heading()
        updated = heading.with_diagnostic("note one").with_diagnostic("note two")
        self.assertEqual(updated.diagnostics, ("note one", "note two"))
        self.assertEqual(heading.diagnostics, ())  # original untouched

    def test_with_metadata_merges(self):
        heading = _make_heading(metadata={"a": 1})
        updated = heading.with_metadata(b=2)
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertEqual(heading.metadata, {"a": 1})  # original untouched

    def test_metadata_defensively_copied(self):
        source = {"a": 1}
        heading = _make_heading(metadata=source)
        source["a"] = 999
        self.assertEqual(heading.metadata, {"a": 1})

    def test_is_canonicalized_false_by_default(self):
        heading = _make_heading()
        self.assertFalse(heading.is_canonicalized)

    def test_is_canonicalized_true_once_type_and_system_set(self):
        heading = _make_heading().with_updates(
            canonical_type=CanonicalHeadingType.SECTION,
            numbering_system=NumberingSystem.ARABIC,
        )
        self.assertTrue(heading.is_canonicalized)

    def test_serialization_roundtrip_via_dataclasses(self):
        import dataclasses
        heading = _make_heading()
        as_dict = dataclasses.asdict(heading)
        self.assertEqual(as_dict["original_text"], "1.1")
        self.assertEqual(as_dict["recognized_classification"], HeadingClassification.NUMBERED)

    # -- M4.2 interop / backwards compatibility --------------------------------------------------

    def test_from_recognition_preserves_m42_fields(self):
        context = RecognitionContext(text="1.1", page=5, book_id="book1", chapter_id="ch1")
        result = RecognitionResult(
            recognizer_name="numbered_heading",
            classification=HeadingClassification.NUMBERED,
            confidence=0.87,
            level=2,
            number="1.1",
            title=None,
        )
        heading = CanonicalHeading.from_recognition(context, result, original_language="en")
        self.assertEqual(heading.original_text, "1.1")
        self.assertEqual(heading.recognized_classification, HeadingClassification.NUMBERED)
        self.assertEqual(heading.recognized_confidence, 0.87)
        self.assertEqual(heading.level, 2)
        self.assertEqual(heading.original_numbering, "1.1")
        self.assertEqual(heading.original_language, "en")
        # canonicalization placeholders left untouched
        self.assertIsNone(heading.canonical_type)
        self.assertIsNone(heading.canonical_number)
        self.assertEqual(heading.numbering_system, NumberingSystem.UNKNOWN)
        self.assertEqual(heading.validation_status, ValidationStatus.PENDING)

    def test_from_recognition_without_language(self):
        context = RecognitionContext(text="Summary")
        result = RecognitionResult(
            recognizer_name="section_keyword",
            classification=HeadingClassification.SECTION_KEYWORD,
            confidence=0.6,
        )
        heading = CanonicalHeading.from_recognition(context, result)
        self.assertIsNone(heading.original_language)
        self.assertIsNone(heading.level)
        self.assertIsNone(heading.original_numbering)


# ===========================================================================
# validation contracts
# ===========================================================================

class ValidationTest(unittest.TestCase):
    def test_empty_result_is_success(self):
        result = ValidationResult()
        self.assertEqual(result.status, ValidationStatus.SUCCESS)
        self.assertTrue(result.is_success)
        self.assertFalse(result.has_errors)
        self.assertFalse(result.has_warnings)

    def test_success_singleton(self):
        self.assertTrue(SUCCESS.is_success)
        self.assertEqual(SUCCESS.diagnostics, ())

    def test_warning_status(self):
        diag = ValidationDiagnostic(ValidationSeverity.WARNING, "W001", "hmm")
        result = ValidationResult(diagnostics=(diag,))
        self.assertEqual(result.status, ValidationStatus.WARNING)
        self.assertTrue(result.has_warnings)
        self.assertFalse(result.has_errors)

    def test_error_status_dominates_warning(self):
        warn = ValidationDiagnostic(ValidationSeverity.WARNING, "W001", "hmm")
        err = ValidationDiagnostic(ValidationSeverity.ERROR, "E001", "bad")
        result = ValidationResult(diagnostics=(warn, err))
        self.assertEqual(result.status, ValidationStatus.ERROR)
        self.assertTrue(result.has_errors)
        self.assertEqual(len(result.errors()), 1)
        self.assertEqual(len(result.warnings()), 1)

    def test_merged_with_preserves_order(self):
        a = ValidationResult(diagnostics=(ValidationDiagnostic(ValidationSeverity.INFO, "A", "a"),))
        b = ValidationResult(diagnostics=(ValidationDiagnostic(ValidationSeverity.WARNING, "B", "b"),))
        merged = a.merged_with(b)
        self.assertEqual([d.code for d in merged.diagnostics], ["A", "B"])
        # inputs untouched
        self.assertEqual(len(a.diagnostics), 1)
        self.assertEqual(len(b.diagnostics), 1)

    def test_diagnostic_requires_code_and_message(self):
        with self.assertRaises(ValueError):
            ValidationDiagnostic(ValidationSeverity.ERROR, "", "message")
        with self.assertRaises(ValueError):
            ValidationDiagnostic(ValidationSeverity.ERROR, "CODE", "")


# ===========================================================================
# base — CanonicalizationContext / CanonicalizationFailure / HeadingCanonicalizer
# ===========================================================================

class ContextTest(unittest.TestCase):
    def test_defaults(self):
        ctx = CanonicalizationContext()
        self.assertIsNone(ctx.book_id)
        self.assertEqual(ctx.metadata, {})

    def test_metadata_defensively_copied(self):
        source = {"x": 1}
        ctx = CanonicalizationContext(metadata=source)
        source["x"] = 999
        self.assertEqual(ctx.metadata, {"x": 1})

    def test_with_metadata_returns_new_instance(self):
        ctx = CanonicalizationContext(book_id="b1", metadata={"a": 1})
        updated = ctx.with_metadata(b=2)
        self.assertIsNot(ctx, updated)
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertEqual(ctx.metadata, {"a": 1})
        self.assertEqual(updated.book_id, "b1")

    def test_immutable(self):
        ctx = CanonicalizationContext()
        with self.assertRaises(Exception):
            ctx.book_id = "changed"  # type: ignore[misc]


class CanonicalizationFailureTest(unittest.TestCase):
    def test_requires_name(self):
        with self.assertRaises(ValueError):
            CanonicalizationFailure(canonicalizer_name="", reason="x")

    def test_requires_reason(self):
        with self.assertRaises(ValueError):
            CanonicalizationFailure(canonicalizer_name="c1", reason="")

    def test_diagnostics_tupleized(self):
        failure = CanonicalizationFailure(canonicalizer_name="c1", reason="broke", diagnostics=["a", "b"])
        self.assertEqual(failure.diagnostics, ("a", "b"))


class HeadingCanonicalizerTest(unittest.TestCase):
    def test_supports_default_true(self):
        c = _AlwaysAppliesCanonicalizer()
        self.assertTrue(c.supports(_make_heading(), CanonicalizationContext()))

    def test_safe_canonicalize_wraps_exception(self):
        c = _AlwaysRaisesCanonicalizer()
        with self.assertRaises(CanonicalizerExecutionError):
            c.safe_canonicalize(_make_heading(), CanonicalizationContext())

    def test_safe_canonicalize_passthrough_on_success(self):
        c = _AlwaysAppliesCanonicalizer(value="42")
        result = c.safe_canonicalize(_make_heading(), CanonicalizationContext())
        self.assertEqual(result.canonical_number, "42")

    def test_cannot_instantiate_abstract_base(self):
        with self.assertRaises(TypeError):
            HeadingCanonicalizer()  # type: ignore[abstract]


# ===========================================================================
# config
# ===========================================================================

class ConfigTest(unittest.TestCase):
    def test_default_config_usable(self):
        cfg = default_config()
        settings = cfg.settings_for("anything")
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.priority, 100)

    def test_settings_immutable(self):
        settings = CanonicalizerSettings(name="c1")
        with self.assertRaises(Exception):
            settings.priority = 5  # type: ignore[misc]

    def test_settings_requires_name(self):
        with self.assertRaises(CanonicalizerConfigurationError):
            CanonicalizerSettings(name="")

    def test_settings_priority_must_be_int(self):
        with self.assertRaises(CanonicalizerConfigurationError):
            CanonicalizerSettings(name="c1", priority="high")  # type: ignore[arg-type]

    def test_with_overrides(self):
        settings = CanonicalizerSettings(name="c1", priority=10)
        updated = settings.with_overrides(priority=20)
        self.assertEqual(settings.priority, 10)
        self.assertEqual(updated.priority, 20)

    def test_with_canonicalizer_settings(self):
        cfg = default_config()
        new_settings = CanonicalizerSettings(name="c1", enabled=False)
        updated_cfg = cfg.with_canonicalizer_settings(new_settings)
        self.assertTrue(cfg.settings_for("c1").enabled)  # original untouched
        self.assertFalse(updated_cfg.settings_for("c1").enabled)

    def test_with_feature_toggle(self):
        cfg = default_config()
        updated = cfg.with_feature_toggle("my_feature", True)
        self.assertFalse(cfg.is_feature_enabled("my_feature"))
        self.assertTrue(updated.is_feature_enabled("my_feature"))

    def test_extra_defensively_copied(self):
        source = {"k": 1}
        settings = CanonicalizerSettings(name="c1", extra=source)
        source["k"] = 999
        self.assertEqual(settings.extra, {"k": 1})


# ===========================================================================
# registry
# ===========================================================================

class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = CanonicalizerRegistry()

    def test_register_and_get(self):
        c = _AlwaysAppliesCanonicalizer()
        self.registry.register(c)
        self.assertIs(self.registry.get("always_applies"), c)
        self.assertIn("always_applies", self.registry)
        self.assertEqual(len(self.registry), 1)

    def test_duplicate_registration_rejected(self):
        self.registry.register(_AlwaysAppliesCanonicalizer())
        with self.assertRaises(CanonicalizerRegistrationError):
            self.registry.register(_AlwaysAppliesCanonicalizer())

    def test_register_rejects_non_canonicalizer(self):
        with self.assertRaises(CanonicalizerRegistrationError):
            self.registry.register(object())  # type: ignore[arg-type]

    def test_unregister(self):
        self.registry.register(_AlwaysAppliesCanonicalizer())
        self.registry.unregister("always_applies")
        self.assertNotIn("always_applies", self.registry)

    def test_unregister_missing_raises(self):
        with self.assertRaises(CanonicalizerLookupError):
            self.registry.unregister("nope")

    def test_get_missing_raises(self):
        with self.assertRaises(CanonicalizerLookupError):
            self.registry.get("nope")

    def test_lifecycle_enable_disable_mark_failed(self):
        self.registry.register(_NeverAppliesCanonicalizer())
        self.assertEqual(self.registry.state_of("never_applies"), CanonicalizerState.ENABLED)
        self.registry.disable("never_applies")
        self.assertFalse(self.registry.is_enabled("never_applies"))
        self.registry.enable("never_applies")
        self.assertTrue(self.registry.is_enabled("never_applies"))
        self.registry.mark_failed("never_applies")
        self.assertEqual(self.registry.state_of("never_applies"), CanonicalizerState.FAILED)
        self.assertFalse(self.registry.is_enabled("never_applies"))

    def test_deterministic_priority_ordering(self):
        cfg = default_config(canonicalizer_settings={
            "c_low": CanonicalizerSettings(name="c_low", priority=50),
            "c_high": CanonicalizerSettings(name="c_high", priority=10),
        })
        registry = CanonicalizerRegistry(config=cfg)
        registry.register(_AlwaysAppliesCanonicalizer(name="c_low"))
        registry.register(_AlwaysAppliesCanonicalizer(name="c_high"))
        ordered = [c.name for c in registry.all_canonicalizers()]
        self.assertEqual(ordered, ["c_high", "c_low"])

    def test_registration_order_tiebreak(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer(name="first"))
        registry.register(_AlwaysAppliesCanonicalizer(name="second"))
        ordered = [c.name for c in registry.all_canonicalizers()]
        self.assertEqual(ordered, ["first", "second"])

    def test_enabled_canonicalizers_excludes_disabled(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer(name="a"))
        registry.register(_NeverAppliesCanonicalizer())
        registry.disable("never_applies")
        names = [c.name for c in registry.enabled_canonicalizers()]
        self.assertEqual(names, ["a"])

    def test_with_config_preserves_registrations(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer(name="a"))
        new_cfg = default_config(canonicalizer_settings={
            "a": CanonicalizerSettings(name="a", enabled=False),
        })
        new_registry = registry.with_config(new_cfg)
        self.assertIsNot(registry, new_registry)
        self.assertTrue(registry.is_enabled("a"))  # original untouched
        self.assertFalse(new_registry.is_enabled("a"))


# ===========================================================================
# pipeline
# ===========================================================================

class PipelineTest(unittest.TestCase):
    def test_applied_outcome_updates_heading(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer(value="1.1"))
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertEqual(result.output_heading.canonical_number, "1.1")
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].outcome, CanonicalizationOutcome.APPLIED)
        self.assertEqual(result.applied_canonicalizer_names, ("always_applies",))

    def test_unchanged_outcome_leaves_heading(self):
        registry = CanonicalizerRegistry()
        registry.register(_NeverAppliesCanonicalizer())
        pipeline = CanonicalizationPipeline(registry)
        heading = _make_heading()
        result = pipeline.run(heading)
        self.assertEqual(result.output_heading, heading)
        self.assertEqual(result.attempts[0].outcome, CanonicalizationOutcome.UNCHANGED)

    def test_failed_canonicalizer_does_not_abort_pipeline(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysRaisesCanonicalizer())
        registry.register(_AlwaysAppliesCanonicalizer(value="ok"))
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        outcomes = [a.outcome for a in result.attempts]
        self.assertEqual(outcomes, [CanonicalizationOutcome.FAILED, CanonicalizationOutcome.APPLIED])
        self.assertEqual(result.output_heading.canonical_number, "ok")
        failure = result.attempts_by_outcome(CanonicalizationOutcome.FAILED)[0].failure
        self.assertIsInstance(failure, CanonicalizationFailure)
        self.assertIn("boom", failure.reason)

    def test_skipped_when_supports_false(self):
        registry = CanonicalizerRegistry()
        registry.register(_UnsupportedCanonicalizer())
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertEqual(result.attempts[0].outcome, CanonicalizationOutcome.SKIPPED)

    def test_supports_raising_recorded_as_failed(self):
        registry = CanonicalizerRegistry()
        registry.register(_SupportsRaisesCanonicalizer())
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertEqual(result.attempts[0].outcome, CanonicalizationOutcome.FAILED)

    def test_disabled_canonicalizer_never_runs(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer())
        registry.disable("always_applies")
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertEqual(result.attempts, ())

    def test_canonicalizers_cooperate_not_compete(self):
        """Unlike RecognitionPipeline (competing recognizers, one
        winner), every applicable canonicalizer contributes, and each
        sees the PREVIOUS canonicalizer's output."""
        registry = CanonicalizerRegistry()
        registry.register(_AppendDiagnosticCanonicalizer("first", "note-1"))
        registry.register(_AppendDiagnosticCanonicalizer("second", "note-2"))
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertEqual(result.output_heading.diagnostics, ("note-1", "note-2"))
        self.assertEqual(len(result.attempts), 2)
        self.assertTrue(all(a.outcome == CanonicalizationOutcome.APPLIED for a in result.attempts))

    def test_deterministic_across_repeated_runs(self):
        registry = CanonicalizerRegistry()
        registry.register(_AppendDiagnosticCanonicalizer("first", "note-1"))
        registry.register(_AlwaysAppliesCanonicalizer(value="1.1"))
        pipeline = CanonicalizationPipeline(registry)
        heading = _make_heading()
        result_a = pipeline.run(heading)
        result_b = pipeline.run(heading)
        self.assertEqual(result_a.output_heading, result_b.output_heading)
        self.assertEqual(
            [a.outcome for a in result_a.attempts],
            [a.outcome for a in result_b.attempts],
        )

    def test_deterministic_across_independent_pipelines(self):
        def build_registry():
            r = CanonicalizerRegistry()
            r.register(_AlwaysAppliesCanonicalizer(value="1.1"))
            return r

        heading = _make_heading()
        result_a = CanonicalizationPipeline(build_registry()).run(heading)
        result_b = CanonicalizationPipeline(build_registry()).run(heading)
        self.assertEqual(result_a.output_heading, result_b.output_heading)

    def test_input_heading_untouched(self):
        registry = CanonicalizerRegistry()
        registry.register(_AlwaysAppliesCanonicalizer(value="1.1"))
        pipeline = CanonicalizationPipeline(registry)
        heading = _make_heading()
        result = pipeline.run(heading)
        self.assertIsNone(heading.canonical_number)  # original untouched
        self.assertEqual(result.input_heading, heading)
        self.assertEqual(result.output_heading.canonical_number, "1.1")

    def test_context_defaults_when_not_provided(self):
        registry = CanonicalizerRegistry()
        registry.register(_NeverAppliesCanonicalizer())
        pipeline = CanonicalizationPipeline(registry)
        result = pipeline.run(_make_heading())
        self.assertIsInstance(result.context, CanonicalizationContext)

    def test_attempt_record_requires_heading_when_applied(self):
        with self.assertRaises(ValueError):
            AttemptRecord("c1", CanonicalizationOutcome.APPLIED, heading=None)

    def test_attempt_record_requires_failure_when_failed(self):
        with self.assertRaises(ValueError):
            AttemptRecord("c1", CanonicalizationOutcome.FAILED, failure=None)


# ===========================================================================
# public API surface
# ===========================================================================

class PublicApiTest(unittest.TestCase):
    def test_top_level_exports_present(self):
        import modules.heading_canonicalization as hc
        expected = {
            "CanonicalHeading", "ValidationDiagnostic", "ValidationResult", "SUCCESS",
            "CanonicalizationContext", "CanonicalizationFailure", "HeadingCanonicalizer",
            "HeadingCanonicalizationConfig", "CanonicalizerSettings", "default_config",
            "CanonicalizerRegistry", "default_registry", "register", "unregister", "get",
            "enabled_canonicalizers", "all_canonicalizers",
            "CanonicalizationPipeline", "CanonicalizationPipelineResult", "AttemptRecord",
            # M4.3B: the first concrete canonicalizers, registered into
            # default_registry (see test_m43b_number_system_canonicalization.py).
            "NumberingSystemDetector", "RomanNumeralCanonicalizer",
            "ArabicNumeralCanonicalizer", "DevanagariNumeralCanonicalizer",
            "CanonicalHeadingType", "NumberingSystem", "ValidationStatus", "ValidationSeverity",
            "CanonicalizerState", "CanonicalizationOutcome",
            "HeadingCanonicalizationError", "CanonicalizerRegistrationError",
            "CanonicalizerConfigurationError", "CanonicalizerLookupError",
            "CanonicalizerExecutionError", "CanonicalizationPipelineError",
            "CanonicalHeadingValidationError",
            # M4.3D: the structural validator, registered into
            # default_registry (see test_m43d_structural_validation.py).
            "StructuralValidator", "PRECEDING_LEVEL_METADATA_KEY",
        }
        for name in expected:
            self.assertTrue(hasattr(hc, name), f"missing public export: {name}")
        self.assertEqual(set(hc.__all__), expected)

    def test_default_registry_has_m43b_canonicalizers_registered(self):
        # M4.3A itself registered no concrete canonicalizer
        # (framework only). M4.3B (Number System Canonicalization) is
        # the first milestone to plug concrete canonicalizers into
        # this same default_registry, exactly as this package's own
        # README/docstring anticipated: "once M4.3B ... register
        # canonicalizers into default_registry, the exact same
        # pipeline call starts returning a CanonicalHeading with
        # those placeholders actually filled in." This test now pins
        # *that* contract instead of the now-superseded "starts empty"
        # one — see test_m43b_number_system_canonicalization.py for
        # full coverage of the canonicalizers themselves.
        #
        # M4.3D (Structural Validation) adds exactly one more entry --
        # "structural_validator" -- to this same registry, same
        # convention, same one-line register() call; see
        # test_m43d_structural_validation.py for its own coverage.
        import modules.heading_canonicalization as hc
        names = set(hc.default_registry.registered_names())
        self.assertEqual(
            names,
            {
                "numbering_system_detector",
                "roman_numeral_canonicalizer",
                "arabic_numeral_canonicalizer",
                "devanagari_numeral_canonicalizer",
                "structural_validator",
            },
        )

    def test_heading_recognizers_package_untouched_still_importable(self):
        # Sanity: importing this new package must not break importing
        # the frozen M4.2 package, and must not require modifying it.
        import modules.heading_recognizers as hr
        self.assertTrue(hasattr(hr, "RecognitionPipeline"))
        self.assertTrue(hasattr(hr, "default_registry"))


if __name__ == "__main__":
    unittest.main()
