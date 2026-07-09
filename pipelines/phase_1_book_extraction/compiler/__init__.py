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
    "ENRICHMENT_VERSION",
    "ENRICHMENT_FIELDS",
    "EDUCATIONAL_ROLE_BY_OBJECT_TYPE",
    "compute_enrichment",
    "enrich_item",
    "enrich_registry",
    "enrich_registries",
]