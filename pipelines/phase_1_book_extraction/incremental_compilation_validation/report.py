"""
incremental_compilation_validation/report.py — Phase E5.1: Incremental
Compilation Validation Report.

SCOPE: `IncrementalCompilationValidationReport` is the full Phase E5.1
artifact -- purely a data holder, matching every earlier phase's own
"dataclass + to_dict(), all actual computation happens in the owning
validator.py/engine.py" convention (incremental_compilation/plan.py's
own IncrementalCompilationPlan, change_detection/report.py's own
ChangeDetectionReport, validation/system_integrity.py's own
SystemIntegrityReport). All construction happens in validator.py's
`validate_incremental_compilation_plan()`, orchestrated by engine.py's
`validate_incremental_compilation()`.

READ-ONLY REPORTING, WITH A VERDICT (mirrors validation/
system_integrity.py's own SystemIntegrityReport precedent, one layer
over, rather than incremental_compilation/plan.py's own plain
"warnings/errors, never a verdict" shape one phase down): this report
VALIDATES the already-computed Phase E4 IncrementalCompilationPlan and
renders one `overall_status` verdict ("pass"/"fail") over it -- it
never rebuilds, replans, or mutates a single field of that plan, the
Phase E3 ChangeDetectionReport, or the Phase E2 DependencyGraph it was
computed from.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


# This module's own version marker -- independent of every other
# *_VERSION/*_SCHEMA_VERSION constant in this codebase (same convention
# incremental_compilation/plan.py's own INCREMENTAL_COMPILATION_PLAN_
# VERSION and validation/system_integrity.py's own SYSTEM_INTEGRITY_
# VERSION already establish). Bump only if this module's own check set
# or report SHAPE changes.
INCREMENTAL_COMPILATION_VALIDATION_VERSION = "E5.1"


@dataclass
class IncrementalCompilationValidationReport:
    """The full Phase E5.1 artifact.

    FIELD NOTES:
    - `namespace`: the same `chapter_reference` the Phase E4
      IncrementalCompilationPlan being validated already carries as its
      own `namespace` field -- reused unchanged, never a second,
      independently computed namespace.
    - `plan_available`: whether an IncrementalCompilationPlan was
      supplied at all and was shaped like
      incremental_compilation.plan.IncrementalCompilationPlan.to_dict()'s
      own output -- `False` degrades every other field below to its
      empty default rather than raising (mirrors every earlier phase's
      own "malformed/missing input is a warning/error finding, never an
      exception" convention).
    - `overall_status`: `"pass"` if zero errors were found and zero
      named checks failed, `"fail"` otherwise -- identical decision
      rule to validation.system_integrity.validate_system_integrity()'s
      own `report.overall_status = "fail" if (report.errors or failed)
      else "pass"`, one layer over.
    - `errors` / `warnings`: `{"severity", "rule", "message", ["details"]}`
      dicts, exactly validation/system_integrity.py's own `_error()`/
      `_warning()` shape -- reused unchanged rather than inventing a
      second issue shape for this one phase.
    - `checks_passed` / `checks_failed`: the name of every named check
      this module ran, split by outcome -- a check this module could
      not run at all (its own required input was missing) is omitted
      from both lists, never defaulted to "passed" (mirrors
      validation/system_integrity.py's own Finding 3 precedent).
    - `classification_consistency` / `reference_consistency` /
      `ordering_consistency` / `reason_consistency` /
      `determinism_consistency` / `read_only_consistency`: small,
      denormalized detail blocks, one per check group below -- same
      "structured detail alongside the flat errors/warnings/checks_*
      lists" shape validation/system_integrity.py's own six
      `*_consistency` fields already establish, one layer down.
    - `summary`: one human-readable sentence describing the verdict and
      check counts -- same shape validation/system_integrity.py's own
      `report.summary` string already establishes.
    - `incremental_compilation_validation_version`: this module's own
      INCREMENTAL_COMPILATION_VALIDATION_VERSION, stamped per-instance.
    """

    generated_at: str = ""
    incremental_compilation_validation_version: str = INCREMENTAL_COMPILATION_VALIDATION_VERSION
    namespace: str = ""
    plan_available: bool = False
    overall_status: str = "unknown"  # "pass" | "fail" | "unknown"
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    classification_consistency: Dict[str, Any] = field(default_factory=dict)
    reference_consistency: Dict[str, Any] = field(default_factory=dict)
    ordering_consistency: Dict[str, Any] = field(default_factory=dict)
    reason_consistency: Dict[str, Any] = field(default_factory=dict)
    determinism_consistency: Dict[str, Any] = field(default_factory=dict)
    read_only_consistency: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)