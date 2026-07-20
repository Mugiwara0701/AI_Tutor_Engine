"""
teacher_knowledge_base/state.py — M6.1: TKB module-level state.

Follows the exact set_current_*()/get_current_*()/has_current_*()/
reset_*_state() idiom every other phase's own state.py in this codebase
already uses (see artifact_manager/state.py, build_executor/state.py).

RUN-SCOPED, LIKE artifact_manager/state.py: a TeacherKnowledgeBase artifact
describes one whole TKB build run (which may span multiple chapters), so
this state is set once per TKB build (by engine.run()), not once per chapter.

Two independent slots:
  - current TKBSerializationResult (the built artifact and its serialization)
  - current validation result (bool — did the last build pass validation?)

Not thread-safe / not concurrency-safe by design, same explicit note as
every module this mirrors.
"""
from __future__ import annotations

from typing import Any, Optional

_CURRENT_TKB_RESULT: Optional[Any] = None   # TKBSerializationResult
_CURRENT_VALIDATION_PASSED: Optional[bool] = None


# ---------------------------------------------------------------------------
# TKBSerializationResult slot
# ---------------------------------------------------------------------------

def set_current_tkb_result(result: Any) -> None:
    """Called once by engine.run() after the TKB artifact has been
    serialized and validated."""
    global _CURRENT_TKB_RESULT
    _CURRENT_TKB_RESULT = result


def get_current_tkb_result() -> Optional[Any]:
    """Returns the most-recently produced TKBSerializationResult, or None
    if no TKB build has completed in this process."""
    return _CURRENT_TKB_RESULT


def has_current_tkb_result() -> bool:
    """True once set_current_tkb_result() has been called."""
    return _CURRENT_TKB_RESULT is not None


def reset_tkb_result_state() -> None:
    """Clears the TKB result state. Safe to call even if nothing was set."""
    global _CURRENT_TKB_RESULT
    _CURRENT_TKB_RESULT = None


# ---------------------------------------------------------------------------
# Validation result slot
# ---------------------------------------------------------------------------

def set_current_validation_passed(passed: bool) -> None:
    global _CURRENT_VALIDATION_PASSED
    _CURRENT_VALIDATION_PASSED = passed


def get_current_validation_passed() -> Optional[bool]:
    return _CURRENT_VALIDATION_PASSED


def has_current_validation_passed() -> bool:
    return _CURRENT_VALIDATION_PASSED is not None


def reset_validation_state() -> None:
    global _CURRENT_VALIDATION_PASSED
    _CURRENT_VALIDATION_PASSED = None


# ---------------------------------------------------------------------------
# Composite reset
# ---------------------------------------------------------------------------

def reset_all_tkb_state() -> None:
    """Clears both TKB state slots. Safe to call before a new TKB build."""
    reset_tkb_result_state()
    reset_validation_state()
