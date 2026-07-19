"""
modules/educational_taxonomy — M5.2A: the Universal Educational
Taxonomy.

Defines the canonical, curriculum-independent ontology every
educational object in every subject belongs to: seven top-level
`EducationalCategory` values, and a built-in catalog of concrete
`EducationalObjectType` entries (Concept, Definition, Theorem, Proof,
Figure, Table, MCQ, Poem, ...) registered into a `TaxonomyRegistry`.

This package is TAXONOMY ONLY (M5.2A's scope). It does NOT process
any educational object — no extraction, no recognition, no
classification logic. It only *defines* the vocabulary later
milestones classify objects into:

- M5.2B (Subject Profile Framework) maps subject-specific concerns
  onto this same taxonomy without subclassing or duplicating it.
- M5.2C+ (Structural/Semantic/Relationship engines, concrete
  processors) will look objects' `object_type` up against this
  taxonomy via `get()` rather than hard-coding type name strings.

Relationship to M5.1 (`modules.educational_object_framework`, frozen):
this package does not duplicate M5.1's `ProcessingContext`,
`ProcessingPipeline`, processor `ProcessorRegistry`, or configuration
mechanism — it has no processing concern at all. The one concrete
integration point is `validation.py`, which reuses M5.1's own
`ValidationResult` / `ValidationDiagnostic` / `DiagnosticSeverity`
contracts for the taxonomy's own integrity checks rather than
defining a parallel set.

Public API:
    EducationalCategory                          — enums.py
    EducationalObjectType, DEFAULT_TYPE_VERSION  — models.py
    TaxonomyRegistry, default_taxonomy,
    register, unregister, get,
    all_types, types_by_category                 — registry.py
    validate_taxonomy                             — validation.py
    EducationalTaxonomyError and subclasses       — exceptions.py
"""
from modules.educational_taxonomy.enums import EducationalCategory
from modules.educational_taxonomy.exceptions import (
    EducationalTaxonomyError,
    TaxonomyLookupError,
    TaxonomyRegistrationError,
    TaxonomyValidationError,
)
from modules.educational_taxonomy.models import (
    DEFAULT_TYPE_VERSION,
    EducationalObjectType,
)
from modules.educational_taxonomy.registry import (
    TaxonomyRegistry,
    all_types,
    default_taxonomy,
    get,
    register,
    types_by_category,
    unregister,
)
from modules.educational_taxonomy.validation import validate_taxonomy

__all__ = [
    # enums
    "EducationalCategory",
    # models
    "EducationalObjectType",
    "DEFAULT_TYPE_VERSION",
    # registry
    "TaxonomyRegistry",
    "default_taxonomy",
    "register",
    "unregister",
    "get",
    "all_types",
    "types_by_category",
    # validation
    "validate_taxonomy",
    # exceptions
    "EducationalTaxonomyError",
    "TaxonomyRegistrationError",
    "TaxonomyLookupError",
    "TaxonomyValidationError",
]
