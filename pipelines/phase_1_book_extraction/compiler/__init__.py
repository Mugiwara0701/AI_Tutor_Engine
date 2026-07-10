"""
compiler/ — the AI Tutor Compiler's Symbol Table layer.

Phase B0 (complete): generic registry infrastructure -- CanonicalRegistry[T]
and RegistryManager -- with no knowledge of any specific educational
object type (Concept, Figure, Equation, ...).

Phase B1 (this package, currently): concrete per-type registries
(ConceptRegistry, FigureRegistry, EquationRegistry, ...) built on top of
CanonicalRegistry (see compiler/registries.py), plus create_registry_manager()/
populate_registries() -- the glue pipeline.py uses to build one
RegistryManager per chapter and insert every canonical object it builds
into the matching registry.

Usage (generic, B0):

    from compiler import CanonicalRegistry, RegistryManager

    registry = CanonicalRegistry(name="example")
    registry.insert({"id": "abc-123", "urn": "urn:...", "name": "Example"})
    registry.get_by_name("Example")

    manager = RegistryManager()
    manager.create("example")
    manager.get("example").insert({"id": "abc-123", "name": "Example"})

Usage (concrete, B1):

    from compiler import create_registry_manager, populate_registries

    manager = create_registry_manager()
    populate_registries(manager, concepts=all_concepts, figures=figures, ...)
    manager.get("concepts").get_by_name("Photosynthesis")

Usage (lifecycle, B1 refinement -- see compiler/state.py for the full
ownership contract): once pipeline.py populates a chapter's manager, it
calls set_current_registry_manager(manager) so any later, in-process
phase can retrieve that same instance instead of rebuilding it:

    from compiler import get_current_registry_manager

    manager = get_current_registry_manager()  # None if no chapter yet

Package exports (audit refinement): the imports/`__all__` below cover
every public symbol from every completed Phase B module -- B0
(registry.py, registry_manager.py, exceptions.py), B1 (registries.py),
B1's state.py lifecycle (all `_CURRENT_*` get/set/has helpers, not just
the RegistryManager ones), B1b (enrichment.py), B1c (normalization.py),
B2 (references.py), B3 (relationships.py), B4 (validation.py), B5.1
(build.py), B5.2 (fingerprints.py), and B5.3 (finalize.py) -- so
`from compiler import <anything public>` works uniformly regardless of
which phase a symbol was introduced in. Nothing here is reorganized;
this only adds import/`__all__` lines for symbols that already existed
in their own modules.
"""
from .registry import (
    CanonicalRegistry,
    RegistryDiagnostic,
    RegistryStatistics,
)
from .registry_manager import RegistryManager
from .exceptions import (
    RegistryError,
    DuplicateIdError,
    DuplicateUrnError,
    DuplicateNameError,
    ItemNotFoundError,
    RegistrySerializationError,
)
from .registries import (
    ConceptRegistry,
    DefinitionRegistry,
    GlossaryRegistry,
    EquationRegistry,
    FigureRegistry,
    DiagramRegistry,
    TableRegistry,
    ExampleRegistry,
    ActivityRegistry,
    BoxRegistry,
    NoteRegistry,
    WarningRegistry,
    REGISTRY_NAMES,
    create_registry_manager,
    populate_registries,
)
from .state import (
    set_current_registry_manager,
    get_current_registry_manager,
    has_current_registry_manager,
    reset_registry_state,
    set_current_validation_report,
    get_current_validation_report,
    has_current_validation_report,
    set_current_compiler_manifest,
    get_current_compiler_manifest,
    has_current_compiler_manifest,
    set_current_compiler_statistics,
    get_current_compiler_statistics,
    has_current_compiler_statistics,
    set_current_registry_fingerprints,
    get_current_registry_fingerprints,
    has_current_registry_fingerprints,
    set_current_compiler_fingerprint,
    get_current_compiler_fingerprint,
    has_current_compiler_fingerprint,
    set_current_compiler_readiness_report,
    get_current_compiler_readiness_report,
    has_current_compiler_readiness_report,
    set_current_compiler_build_summary,
    get_current_compiler_build_summary,
    has_current_compiler_build_summary,
    set_current_final_compiler_status,
    get_current_final_compiler_status,
    has_current_final_compiler_status,
)
from .enrichment import (
    ENRICHMENT_VERSION,
    ENRICHMENT_FIELDS,
    EDUCATIONAL_ROLE_BY_OBJECT_TYPE,
    compute_enrichment,
    enrich_item,
    enrich_registry,
    enrich_registries,
)
from .normalization import (
    NORMALIZATION_VERSION,
    NORMALIZATION_FIELDS,
    normalize_text,
    canonical_lookup_key,
    compute_normalization,
    normalize_item,
    normalize_registry,
    normalize_registries,
)
from .references import (
    REFERENCE_RESOLUTION_VERSION,
    REFERENCE_FIELDS,
    resolve_registries,
    resolve_topic_concept_ids,
    verify_topic_references,
    resolve_references,
)
from .relationships import (
    RELATIONSHIP_RESOLUTION_VERSION,
    RELATIONSHIP_REGISTRY_NAME,
    RELATIONSHIP_TYPES,
    RelationshipRegistry,
    ensure_relationship_registry,
    resolve_relationships,
)
from .validation import (
    VALIDATION_VERSION,
    ValidationIssue,
    ValidationReport,
    validate_compiler_state,
)
from .build import (
    COMPILER_VERSION,
    BUILD_VERSION,
    CompilerManifest,
    generate_compiler_manifest,
    CompilerStatistics,
    generate_compiler_statistics,
)
from .fingerprints import (
    FINGERPRINT_VERSION,
    generate_registry_fingerprints,
    generate_compiler_fingerprint,
    CompilerReadinessReport,
    generate_compiler_readiness_report,
    generate_compiler_fingerprints,
)
from .finalize import (
    FINALIZE_VERSION,
    STATUS_READY,
    STATUS_READY_WITH_WARNINGS,
    STATUS_FAILED,
    CompilerBuildSummary,
    determine_final_compiler_status,
    generate_compiler_build_summary,
    finalize_compiler_build,
)

__all__ = [
    "CanonicalRegistry",
    "RegistryDiagnostic",
    "RegistryStatistics",
    "RegistryManager",
    "RegistryError",
    "DuplicateIdError",
    "DuplicateUrnError",
    "DuplicateNameError",
    "ItemNotFoundError",
    "RegistrySerializationError",
    "ConceptRegistry",
    "DefinitionRegistry",
    "GlossaryRegistry",
    "EquationRegistry",
    "FigureRegistry",
    "DiagramRegistry",
    "TableRegistry",
    "ExampleRegistry",
    "ActivityRegistry",
    "BoxRegistry",
    "NoteRegistry",
    "WarningRegistry",
    "REGISTRY_NAMES",
    "create_registry_manager",
    "populate_registries",
    "set_current_registry_manager",
    "get_current_registry_manager",
    "has_current_registry_manager",
    "reset_registry_state",
    "set_current_validation_report",
    "get_current_validation_report",
    "has_current_validation_report",
    "set_current_compiler_manifest",
    "get_current_compiler_manifest",
    "has_current_compiler_manifest",
    "set_current_compiler_statistics",
    "get_current_compiler_statistics",
    "has_current_compiler_statistics",
    "set_current_registry_fingerprints",
    "get_current_registry_fingerprints",
    "has_current_registry_fingerprints",
    "set_current_compiler_fingerprint",
    "get_current_compiler_fingerprint",
    "has_current_compiler_fingerprint",
    "set_current_compiler_readiness_report",
    "get_current_compiler_readiness_report",
    "has_current_compiler_readiness_report",
    "set_current_compiler_build_summary",
    "get_current_compiler_build_summary",
    "has_current_compiler_build_summary",
    "set_current_final_compiler_status",
    "get_current_final_compiler_status",
    "has_current_final_compiler_status",
    "ENRICHMENT_VERSION",
    "ENRICHMENT_FIELDS",
    "EDUCATIONAL_ROLE_BY_OBJECT_TYPE",
    "compute_enrichment",
    "enrich_item",
    "enrich_registry",
    "enrich_registries",
    "NORMALIZATION_VERSION",
    "NORMALIZATION_FIELDS",
    "normalize_text",
    "canonical_lookup_key",
    "compute_normalization",
    "normalize_item",
    "normalize_registry",
    "normalize_registries",
    "REFERENCE_RESOLUTION_VERSION",
    "REFERENCE_FIELDS",
    "resolve_registries",
    "resolve_topic_concept_ids",
    "verify_topic_references",
    "resolve_references",
    "RELATIONSHIP_RESOLUTION_VERSION",
    "RELATIONSHIP_REGISTRY_NAME",
    "RELATIONSHIP_TYPES",
    "RelationshipRegistry",
    "ensure_relationship_registry",
    "resolve_relationships",
    "VALIDATION_VERSION",
    "ValidationIssue",
    "ValidationReport",
    "validate_compiler_state",
    "COMPILER_VERSION",
    "BUILD_VERSION",
    "CompilerManifest",
    "generate_compiler_manifest",
    "CompilerStatistics",
    "generate_compiler_statistics",
    "FINGERPRINT_VERSION",
    "generate_registry_fingerprints",
    "generate_compiler_fingerprint",
    "CompilerReadinessReport",
    "generate_compiler_readiness_report",
    "generate_compiler_fingerprints",
    "FINALIZE_VERSION",
    "STATUS_READY",
    "STATUS_READY_WITH_WARNINGS",
    "STATUS_FAILED",
    "CompilerBuildSummary",
    "determine_final_compiler_status",
    "generate_compiler_build_summary",
    "finalize_compiler_build",
]