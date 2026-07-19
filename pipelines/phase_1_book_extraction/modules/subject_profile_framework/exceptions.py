"""
modules/subject_profile_framework/exceptions.py — M5.2B: exception
hierarchy for the Subject Profile Extension Framework.

Mirrors `modules.educational_taxonomy.exceptions`'s and
`modules.educational_object_framework.exceptions`'s convention exactly:
a single catch-all base per layer, plus small, specific subclasses so
callers can catch precisely what they care about. This is a
deliberately separate hierarchy from `EducationalTaxonomyError` — a
subject-profile registration problem (duplicate subject, malformed
contribution, a taxonomy extension that was rejected) is a different
concern from a taxonomy-internal problem, even though the two are
related whenever `SubjectProfileRegistry` delegates into the frozen
`TaxonomyRegistry`.
"""


class SubjectProfileFrameworkError(Exception):
    """Base class for every error raised anywhere in the
    subject_profile_framework package. Catch this to handle any
    Subject Profile Framework failure generically."""


class SubjectContributionValidationError(SubjectProfileFrameworkError):
    """Raised by `models.SubjectContribution` / `models.SubjectProfile`
    constructors when a value is structurally invalid — e.g. an empty
    subject_key, a contribution whose subject_key does not match its
    owning profile's, or a malformed version string. Distinct from
    `modules.educational_taxonomy.exceptions.TaxonomyValidationError`,
    which governs the wrapped `EducationalObjectType` itself."""


class SubjectProfileRegistrationError(SubjectProfileFrameworkError):
    """Raised by `SubjectProfileRegistry.register()` when a
    `SubjectProfile` cannot be registered as given — e.g. a duplicate
    subject_key, or a contribution whose object identifier (key or
    alias) collides with another already-registered contribution
    within this same registry."""


class SubjectProfileLookupError(SubjectProfileFrameworkError, LookupError):
    """Raised by `SubjectProfileRegistry` lookup methods when asked for
    a subject_key that is not registered. Subclasses LookupError as
    well, so existing generic `except LookupError` handling elsewhere
    still catches it without modification."""


class TaxonomyExtensionError(SubjectProfileFrameworkError):
    """Wraps a failure raised by the frozen
    `modules.educational_taxonomy.registry.TaxonomyRegistry.register()`
    / `.unregister()` while `SubjectProfileRegistry` was extending the
    taxonomy on a profile's behalf (e.g. a contribution's key or alias
    collides with a built-in taxonomy entry or with a different
    subject's already-registered contribution). Lets a caller catch
    every Subject Profile Framework failure via
    `SubjectProfileFrameworkError` without needing to import
    `modules.educational_taxonomy.exceptions` as well."""


__all__ = [
    "SubjectProfileFrameworkError",
    "SubjectContributionValidationError",
    "SubjectProfileRegistrationError",
    "SubjectProfileLookupError",
    "TaxonomyExtensionError",
]
