"""
modules/educational_taxonomy/exceptions.py — M5.2A: exception
hierarchy for the Universal Educational Taxonomy.

Mirrors modules/educational_object_framework/exceptions.py's
convention exactly: a single catch-all base per layer, plus small,
specific subclasses so callers can catch precisely what they care
about. This is a deliberately separate hierarchy from
`EducationalObjectFrameworkError` — the taxonomy is a data catalog,
not a processing framework, so its errors (a duplicate type key, an
unknown lookup, a structurally invalid entry) are a different concern
than a processor registration or pipeline execution error. A future
concrete processor (M5.2+) that wants to look up a taxonomy entry can
catch `EducationalTaxonomyError` without it being confused for a
framework-level failure, and vice versa.
"""


class EducationalTaxonomyError(Exception):
    """Base class for every error raised anywhere in the
    educational_taxonomy package. Catch this to handle any taxonomy
    failure generically."""


class TaxonomyRegistrationError(EducationalTaxonomyError):
    """Raised by TaxonomyRegistry.register() when an
    EducationalObjectType cannot be registered as given — e.g. a
    duplicate key, a missing/invalid category, or one that fails the
    registry's structural validation."""


class TaxonomyLookupError(EducationalTaxonomyError, LookupError):
    """Raised by TaxonomyRegistry lookup methods when asked for a key
    or category that is not registered. Subclasses LookupError as
    well, so existing generic `except LookupError` handling elsewhere
    still catches it without modification."""


class TaxonomyValidationError(EducationalTaxonomyError):
    """Raised by `models.EducationalObjectType` (or taxonomy-wide
    integrity checks in `validation.py`) when a value is structurally
    invalid — e.g. an empty key, a key not in canonical snake_case
    form, or a category that is not an `EducationalCategory` member."""


__all__ = [
    "EducationalTaxonomyError",
    "TaxonomyRegistrationError",
    "TaxonomyLookupError",
    "TaxonomyValidationError",
]
