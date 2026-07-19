"""
modules/subject_profile_framework — M5.2B: the Subject Profile
Extension Framework.

Extends the frozen M5.2A Universal Educational Taxonomy
(`modules.educational_taxonomy`) with subject-specific educational
object types, metadata, and capability-based queries — without
modifying, subclassing, or redesigning any part of that frozen
package. A `SubjectProfile` bundles one subject's `SubjectContribution`
entries; registering it (via `SubjectProfileRegistry.register()`)
extends `modules.educational_taxonomy.registry.TaxonomyRegistry` by
calling that registry's own, unmodified `register()` for each
contribution's `EducationalObjectType` — the exact mechanism M5.2A
already provides for this purpose.

Relationship to M5.2A (frozen):
    - `EducationalObjectType` is reused exactly as-is; this package
      does not add fields to it, subclass it, or monkeypatch it.
    - `TaxonomyRegistry` is reused exactly as-is; this package never
      adds a method to it or reaches into its private state.
    - `register()` (M5.2A's "sole extension point") is the only way
      this package extends the taxonomy.
    - The richer metadata M5.2A's own spec once envisioned (symbolic
      content, copyright sensitivity, structural/semantic/relationship
      support) but never actually implemented is defined here instead,
      on `SubjectContribution` — an M5.2B-owned layer beside the
      taxonomy, not inside it.
    - Capability-based queries (by category, by symbolic content, by
      support level, ...) live on `SubjectProfileRegistry`, not on
      `TaxonomyRegistry`.

Public API:
    CopyrightSensitivity, SupportLevel, support_at_least  — enums.py
    SubjectContribution, SubjectProfile,
    DEFAULT_CONTRIBUTION_VERSION, DEFAULT_PROFILE_VERSION — models.py
    SubjectProfileRegistry, default_subject_profiles,
    register, unregister, get,
    all_profiles, all_contributions                       — registry.py
    validate_subject_profile_registry                      — validation.py
    SubjectProfileFrameworkError and subclasses             — exceptions.py
"""
from modules.subject_profile_framework.enums import (
    CopyrightSensitivity,
    SupportLevel,
    support_at_least,
)
from modules.subject_profile_framework.exceptions import (
    SubjectContributionValidationError,
    SubjectProfileFrameworkError,
    SubjectProfileLookupError,
    SubjectProfileRegistrationError,
    TaxonomyExtensionError,
)
from modules.subject_profile_framework.models import (
    DEFAULT_CONTRIBUTION_VERSION,
    DEFAULT_PROFILE_VERSION,
    SubjectContribution,
    SubjectProfile,
)
from modules.subject_profile_framework.registry import (
    SubjectProfileRegistry,
    all_contributions,
    all_profiles,
    default_subject_profiles,
    get,
    register,
    unregister,
)
from modules.subject_profile_framework.validation import validate_subject_profile_registry

__all__ = [
    # enums
    "CopyrightSensitivity",
    "SupportLevel",
    "support_at_least",
    # models
    "SubjectContribution",
    "SubjectProfile",
    "DEFAULT_CONTRIBUTION_VERSION",
    "DEFAULT_PROFILE_VERSION",
    # registry
    "SubjectProfileRegistry",
    "default_subject_profiles",
    "register",
    "unregister",
    "get",
    "all_profiles",
    "all_contributions",
    # validation
    "validate_subject_profile_registry",
    # exceptions
    "SubjectProfileFrameworkError",
    "SubjectContributionValidationError",
    "SubjectProfileRegistrationError",
    "SubjectProfileLookupError",
    "TaxonomyExtensionError",
]
