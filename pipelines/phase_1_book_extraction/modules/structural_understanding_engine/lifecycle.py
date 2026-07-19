"""
modules/structural_understanding_engine/lifecycle.py — M5.2C: Subject
Profile lifecycle management.

The lifecycle (REGISTERED -> VALIDATED -> ACTIVE -> INACTIVE ->
UNREGISTERED) belongs entirely to M5.2C. `modules.subject_profile_
framework.models.SubjectProfile` and `.registry.SubjectProfileRegistry`
(both frozen, M5.2B) carry no lifecycle state of their own and are
never modified to add one — `ProfileActivationManager` tracks every
profile's `ProfileLifecycleState` externally, in its own state, keyed
by `subject_key`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional, Set

from modules.educational_object_framework.validation import SUCCESS, ValidationResult
from modules.structural_understanding_engine.compatibility import CompatibilityValidator
from modules.structural_understanding_engine.enums import ProfileLifecycleState
from modules.structural_understanding_engine.exceptions import ProfileLifecycleError

if TYPE_CHECKING:
    from modules.subject_profile_framework.registry import SubjectProfileRegistry

logger = logging.getLogger("ncert_pipeline.structural_understanding_engine")

#: Allowed forward/lateral transitions, keyed by current state.
#: VALIDATED -> REGISTERED lets a profile whose underlying
#: contributions changed be re-validated from scratch; INACTIVE ->
#: ACTIVE is reactivation. UNREGISTERED has no outgoing transition —
#: terminal.
_ALLOWED_TRANSITIONS: Dict[ProfileLifecycleState, Set[ProfileLifecycleState]] = {
    ProfileLifecycleState.REGISTERED: {ProfileLifecycleState.VALIDATED},
    ProfileLifecycleState.VALIDATED: {ProfileLifecycleState.ACTIVE, ProfileLifecycleState.REGISTERED},
    ProfileLifecycleState.ACTIVE: {ProfileLifecycleState.INACTIVE},
    ProfileLifecycleState.INACTIVE: {ProfileLifecycleState.ACTIVE, ProfileLifecycleState.UNREGISTERED},
    ProfileLifecycleState.UNREGISTERED: set(),
}


@dataclass(frozen=True)
class ProfileLifecycleRecord:
    """Immutable snapshot of one subject profile's current lifecycle
    state, returned by `ProfileActivationManager` read methods (never
    mutated in place — every transition produces a fresh record)."""

    subject_key: str
    state: ProfileLifecycleState
    last_validation: ValidationResult = field(default_factory=lambda: SUCCESS)


class ProfileActivationManager:
    """Tracks and transitions every Subject Profile's
    `ProfileLifecycleState`, gated on `CompatibilityValidator` checks
    before allowing ACTIVE. Reads `SubjectProfileRegistry` (M5.2B,
    frozen) to confirm a `subject_key` is actually registered before
    accepting it into the lifecycle — never registers, unregisters, or
    otherwise mutates that registry itself."""

    def __init__(
        self,
        subject_profiles: "SubjectProfileRegistry",
        compatibility_validator: CompatibilityValidator,
    ) -> None:
        self._subject_profiles = subject_profiles
        self._compatibility_validator = compatibility_validator
        self._records: Dict[str, ProfileLifecycleRecord] = {}

    # -- transitions --------------------------------------------------

    def mark_registered(self, subject_key: str) -> ProfileLifecycleRecord:
        """Begins lifecycle tracking for `subject_key`, which must
        already be registered in this manager's `SubjectProfileRegistry`.
        Idempotent if already REGISTERED; raises if further along."""
        profile = self._require_profile(subject_key)
        existing = self._records.get(subject_key)
        if existing is not None and existing.state != ProfileLifecycleState.REGISTERED:
            raise ProfileLifecycleError(
                f"Subject '{subject_key}' is already tracked in state "
                f"'{existing.state.value}'; cannot re-mark as registered."
            )
        record = ProfileLifecycleRecord(subject_key=subject_key, state=ProfileLifecycleState.REGISTERED)
        self._records[subject_key] = record
        logger.debug("Subject '%s' entered lifecycle state REGISTERED.", subject_key)
        return record

    def validate(self, subject_key: str) -> ProfileLifecycleRecord:
        """Runs `CompatibilityValidator.validate_profile()` against
        `subject_key`'s current `SubjectProfile` and transitions
        REGISTERED -> VALIDATED (or VALIDATED -> VALIDATED, a
        re-validation) if the result has no errors; otherwise the
        state remains REGISTERED and the failing `ValidationResult` is
        still recorded for inspection via `state_of()`/`record_for()`."""
        record = self._require_record(subject_key)
        if record.state not in (ProfileLifecycleState.REGISTERED, ProfileLifecycleState.VALIDATED):
            raise ProfileLifecycleError(
                f"Illegal lifecycle transition {record.state.value} -> "
                f"{ProfileLifecycleState.VALIDATED.value}."
            )
        profile = self._require_profile(subject_key)
        result = self._compatibility_validator.validate_profile(profile)
        new_state = ProfileLifecycleState.VALIDATED if result.is_success else ProfileLifecycleState.REGISTERED
        new_record = ProfileLifecycleRecord(subject_key=subject_key, state=new_state, last_validation=result)
        self._records[subject_key] = new_record
        logger.debug(
            "Subject '%s' validation %s -> lifecycle state %s.",
            subject_key, "succeeded" if result.is_success else "failed", new_state.value,
        )
        return new_record

    def activate(self, subject_key: str) -> ProfileLifecycleRecord:
        """Transitions VALIDATED -> ACTIVE. Requires the most recent
        `validate()` call to have succeeded; raises
        `ProfileLifecycleError` otherwise (including if `validate()`
        was never called)."""
        record = self._require_record(subject_key)
        self._require_transition(record.state, ProfileLifecycleState.ACTIVE)
        if not record.last_validation.is_success:
            raise ProfileLifecycleError(
                f"Subject '{subject_key}' cannot be activated: its most recent validation "
                "reported errors."
            )
        new_record = ProfileLifecycleRecord(
            subject_key=subject_key, state=ProfileLifecycleState.ACTIVE, last_validation=record.last_validation,
        )
        self._records[subject_key] = new_record
        logger.debug("Subject '%s' entered lifecycle state ACTIVE.", subject_key)
        return new_record

    def deactivate(self, subject_key: str) -> ProfileLifecycleRecord:
        """Transitions ACTIVE -> INACTIVE."""
        record = self._require_record(subject_key)
        self._require_transition(record.state, ProfileLifecycleState.INACTIVE)
        new_record = ProfileLifecycleRecord(
            subject_key=subject_key, state=ProfileLifecycleState.INACTIVE, last_validation=record.last_validation,
        )
        self._records[subject_key] = new_record
        logger.debug("Subject '%s' entered lifecycle state INACTIVE.", subject_key)
        return new_record

    def reactivate(self, subject_key: str) -> ProfileLifecycleRecord:
        """Transitions INACTIVE -> ACTIVE, re-running compatibility
        validation first (a profile may have drifted while inactive)."""
        record = self._require_record(subject_key)
        self._require_transition(record.state, ProfileLifecycleState.ACTIVE)
        profile = self._require_profile(subject_key)
        result = self._compatibility_validator.validate_profile(profile)
        if not result.is_success:
            self._records[subject_key] = ProfileLifecycleRecord(
                subject_key=subject_key, state=ProfileLifecycleState.INACTIVE, last_validation=result,
            )
            raise ProfileLifecycleError(
                f"Subject '{subject_key}' cannot be reactivated: compatibility re-validation "
                "reported errors."
            )
        new_record = ProfileLifecycleRecord(
            subject_key=subject_key, state=ProfileLifecycleState.ACTIVE, last_validation=result,
        )
        self._records[subject_key] = new_record
        logger.debug("Subject '%s' reactivated -> lifecycle state ACTIVE.", subject_key)
        return new_record

    def unregister(self, subject_key: str) -> ProfileLifecycleRecord:
        """Transitions INACTIVE -> UNREGISTERED (terminal). Does not
        touch `SubjectProfileRegistry` itself — this only ends M5.2C's
        own lifecycle tracking for `subject_key`."""
        record = self._require_record(subject_key)
        self._require_transition(record.state, ProfileLifecycleState.UNREGISTERED)
        new_record = ProfileLifecycleRecord(
            subject_key=subject_key, state=ProfileLifecycleState.UNREGISTERED, last_validation=record.last_validation,
        )
        self._records[subject_key] = new_record
        logger.debug("Subject '%s' entered lifecycle state UNREGISTERED.", subject_key)
        return new_record

    # -- reads --------------------------------------------------

    def state_of(self, subject_key: str) -> ProfileLifecycleState:
        return self._require_record(subject_key).state

    def record_for(self, subject_key: str) -> ProfileLifecycleRecord:
        return self._require_record(subject_key)

    def all_records(self) -> Dict[str, ProfileLifecycleRecord]:
        return dict(self._records)

    def __contains__(self, subject_key: str) -> bool:
        return subject_key in self._records

    # -- internals --------------------------------------------------

    def _require_profile(self, subject_key: str):
        from modules.subject_profile_framework.exceptions import SubjectProfileLookupError
        try:
            return self._subject_profiles.get(subject_key)
        except SubjectProfileLookupError as exc:
            raise ProfileLifecycleError(
                f"Subject '{subject_key}' is not registered in the Subject Profile Registry."
            ) from exc

    def _require_record(self, subject_key: str) -> ProfileLifecycleRecord:
        record = self._records.get(subject_key)
        if record is None:
            raise ProfileLifecycleError(
                f"Subject '{subject_key}' has no lifecycle record; call mark_registered() first."
            )
        return record

    def _require_transition(
        self,
        current: ProfileLifecycleState,
        target: ProfileLifecycleState,
    ) -> None:
        if target not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise ProfileLifecycleError(
                f"Illegal lifecycle transition {current.value} -> {target.value}."
            )


__all__ = [
    "ProfileLifecycleRecord",
    "ProfileActivationManager",
]
