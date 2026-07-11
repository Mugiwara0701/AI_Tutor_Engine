"""
incremental_compilation_validation/engine.py — Phase E5.1: Incremental
Compilation Validation Engine (pipeline.py integration point).

SCOPE: this module is a thin orchestration wrapper around validator.py's
own `validate_incremental_compilation_plan()` -- mirrors
incremental_compilation/engine.py's own division of labor with
planner.py, one phase over (engine.py stamps nothing itself here beyond
what validator.py's own report.py dataclass already stamps; unlike
Phase E4's own engine.py, this module adds no extra provenance field of
its own, since the Phase E5.1 report already carries its own
`namespace`/`generated_at`/version directly).

`validate_incremental_compilation()` is Phase E5.1's own single
pipeline.py integration point, inserted immediately after Phase E4
(incremental_compilation.engine.plan_incremental_compilation()) and
immediately before Phase E5.2 (Incremental Compilation Finalization --
not yet implemented, out of this module's own scope).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .validator import validate_incremental_compilation_plan

# This module's own version marker -- independent of every other
# *_VERSION constant in this codebase (see e.g.
# incremental_compilation/engine.py's own INCREMENTAL_COMPILATION_
# VERSION). Bump only if the SHAPE this module produces itself changes
# in a way a consumer of `incremental_compilation_validation` should be
# able to detect.
INCREMENTAL_COMPILATION_VALIDATION_ENGINE_VERSION = "E5.1"


def validate_incremental_compilation(
    *,
    namespace: str,
    # Phase E4 (Incremental Compilation), already in scope.
    incremental_compilation_plan: Optional[Dict[str, Any]],
    # Phase E2 (Build Dependency Graph), already in scope -- read-only,
    # reused for reference/ordering/determinism checks; never rebuilt
    # or modified.
    dependency_graph: Optional[Dict[str, Any]] = None,
    # Phase E3 (Change Detection), already in scope -- read-only,
    # accepted so this module's own read-only-behaviour check can also
    # cover it (see validator.py's own module docstring).
    change_detection_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase E5.1's single pipeline.py integration point. Must run
    AFTER incremental_compilation.engine.plan_incremental_compilation()
    (so there is a current IncrementalCompilationPlan to validate) and
    is inserted immediately after Phase E4, before Chapter JSON is
    assembled -- see pipeline.py's own comment at the call site.

    Read-only over every argument -- see validator.py's own module
    docstring and `_validate_read_only_behaviour()`. Never executes
    compilation, never rebuilds anything, never modifies the rebuild
    plan, and never generates readiness, final status, or a build
    summary (Phase E5.2's own job, out of this function's scope).

    Returns:
        {
            "incremental_compilation_validation_report": <dict>,  # ready
                # for incremental_compilation_validation.state.
                # set_current_incremental_compilation_validation_report().
        }
    """
    report = validate_incremental_compilation_plan(
        namespace=namespace,
        incremental_compilation_plan=incremental_compilation_plan,
        dependency_graph=dependency_graph,
        change_detection_report=change_detection_report,
    )
    return {"incremental_compilation_validation_report": report}