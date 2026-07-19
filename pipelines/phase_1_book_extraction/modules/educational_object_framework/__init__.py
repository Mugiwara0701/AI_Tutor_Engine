"""
modules/educational_object_framework — M5.1: foundation framework for
educational object processing.

This package is FRAMEWORK ONLY (M5.1's scope), exactly as
`modules.heading_recognizers` was framework-only for M4.2A and
`modules.heading_canonicalization` was framework-only for M4.3A. It
defines the processing context, immutable result model, processor
extension interface, registry, pipeline, configuration, and validation
contracts every concrete educational object processor (M5.2 — an
EquationProcessor, FigureProcessor, TableProcessor, DiagramProcessor,
ExampleProcessor, ActivityProcessor, DefinitionProcessor,
GlossaryProcessor, ...) will use — but implements no concrete
object-specific processing logic itself (no equation extraction, no
figure/table/diagram handling, no cross-object validation; see each
module's own docstring and this package's `README.md` for the full
"Out of Scope" list).

Relationship to the heading subsystem (M4, frozen — see repository
root docs): `heading_recognizers` and `heading_canonicalization`
answer "what heading is this, and what is its canonical form?" for the
document's structural skeleton. This package answers a different
question for the CONTENT that skeleton organizes: "given some
recognized educational object (an equation, a figure, a table, an
example, ...), how should it be processed?" The two subsystems are
architectural siblings, not a pipeline of one into the other — this
package does not import from, depend on, or modify anything in
`heading_recognizers` or `heading_canonicalization`; it mirrors their
module layout and design philosophy only, as the M5.1 spec requires.

Public API:
    ProcessingResult                        — models.py
    ValidationDiagnostic, ValidationResult, SUCCESS
                                             — validation.py
    ProcessingContext, ProcessingFailure,
    EducationalObjectProcessor              — base.py
    EducationalObjectFrameworkConfig,
    ProcessorSettings, default_config       — config.py
    ProcessorRegistry, default_registry,
    register, unregister, get,
    enabled_processors, all_processors      — registry.py
    ProcessingPipeline, ProcessingPipelineResult,
    AttemptRecord                           — pipeline.py
    ProcessorState, ProcessingOutcome,
    DiagnosticSeverity                      — enums.py
    EducationalObjectFrameworkError and subclasses
                                             — exceptions.py

M5.2 will add the first concrete processors, each registered into
`default_registry` via one `register(...)` call, mirroring
`heading_canonicalization`'s own M4.3B registration convention.
Nothing in `base.py`, `config.py`, `registry.py`, or `pipeline.py`
should need to change to add them.
"""
from modules.educational_object_framework.base import (
    EducationalObjectProcessor,
    ProcessingContext,
    ProcessingFailure,
)
from modules.educational_object_framework.config import (
    EducationalObjectFrameworkConfig,
    ProcessorSettings,
    default_config,
)
from modules.educational_object_framework.enums import (
    DiagnosticSeverity,
    ProcessingOutcome,
    ProcessorState,
)
from modules.educational_object_framework.exceptions import (
    EducationalObjectFrameworkError,
    ProcessingPipelineError,
    ProcessingResultValidationError,
    ProcessorConfigurationError,
    ProcessorExecutionError,
    ProcessorLookupError,
    ProcessorRegistrationError,
)
from modules.educational_object_framework.models import ProcessingResult
from modules.educational_object_framework.pipeline import (
    AttemptRecord,
    ProcessingPipeline,
    ProcessingPipelineResult,
)
from modules.educational_object_framework.registry import (
    ProcessorRegistry,
    all_processors,
    default_registry,
    enabled_processors,
    get,
    register,
    unregister,
)
from modules.educational_object_framework.validation import (
    SUCCESS,
    ValidationDiagnostic,
    ValidationResult,
)

__all__ = [
    # models
    "ProcessingResult",
    # validation
    "ValidationDiagnostic",
    "ValidationResult",
    "SUCCESS",
    # base
    "ProcessingContext",
    "ProcessingFailure",
    "EducationalObjectProcessor",
    # config
    "EducationalObjectFrameworkConfig",
    "ProcessorSettings",
    "default_config",
    # registry
    "ProcessorRegistry",
    "default_registry",
    "register",
    "unregister",
    "get",
    "enabled_processors",
    "all_processors",
    # pipeline
    "ProcessingPipeline",
    "ProcessingPipelineResult",
    "AttemptRecord",
    # enums
    "ProcessorState",
    "ProcessingOutcome",
    "DiagnosticSeverity",
    # exceptions
    "EducationalObjectFrameworkError",
    "ProcessorRegistrationError",
    "ProcessorConfigurationError",
    "ProcessorLookupError",
    "ProcessorExecutionError",
    "ProcessingPipelineError",
    "ProcessingResultValidationError",
]
