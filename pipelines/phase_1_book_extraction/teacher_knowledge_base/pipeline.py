"""
teacher_knowledge_base/pipeline.py — M6.1: TKB build pipeline definition.

SCOPE: defines the ordered list of pipeline stages and their execution
dependencies. Each stage is a module with a build(context) function.

PIPELINE ORDER (per M6.1 spec §2):
  OptimizedKnowledgePackage
  ↓ load compiler artifacts
  ↓ build EDST
  ↓ build EDG
  ↓ build EKG
  ↓ build TeachingUnits
  ↓ build ConceptProgressionTemplates
  ↓ build CurriculumGraph
  ↓ build Navigation
  ↓ build RuntimeIndexes
  ↓ Compute Statistics
  ↓ Validation
  ↓ Serialization
  ↓ TeacherKnowledgeBase

Each stage is deterministic. Stages run sequentially (each stage may depend
on outputs of previous stages). No parallel stage execution within one TKB build
— determinism is paramount.

STAGE DESCRIPTOR:
  - name: the context output key this stage writes to
  - module: the builder module (must have a build(context) function)
  - required: if True, failure raises immediately; if False, records warning and continues
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional


@dataclass
class PipelineStage:
    """Descriptor for one TKB pipeline stage."""
    name: str               # context output key
    label: str              # human-readable label for logging/reporting
    build_fn: Callable      # build(context) function
    required: bool = True   # fatal if True and stage fails


def _get_stages() -> List[PipelineStage]:
    """Returns the ordered pipeline stage list. Modules are imported lazily
    to avoid circular imports at module load time."""
    from .builders import edst_builder, ekg_builder, edg_builder
    from .builders import teaching_unit_builder, progression_builder
    from .builders import curriculum_builder, navigation_builder, runtime_index_builder
    from . import statistics, validation

    return [
        PipelineStage(
            name="edst",
            label="Enriched DST Builder",
            build_fn=edst_builder.build,
            required=True,
        ),
        PipelineStage(
            name="edg",
            label="Enriched Dependency Graph Builder",
            build_fn=edg_builder.build,
            required=False,  # Can proceed without EDG — EDG input is optional in EKG/units
        ),
        PipelineStage(
            name="ekg",
            label="Enriched Knowledge Graph Builder",
            build_fn=ekg_builder.build,
            required=True,
        ),
        PipelineStage(
            name="teaching_units",
            label="Teaching Unit Builder",
            build_fn=teaching_unit_builder.build,
            required=True,
        ),
        PipelineStage(
            name="concept_progression_templates",
            label="Concept Progression Template Builder",
            build_fn=progression_builder.build,
            required=False,
        ),
        PipelineStage(
            name="curriculum_graph",
            label="Curriculum Graph Builder",
            build_fn=curriculum_builder.build,
            required=True,
        ),
        PipelineStage(
            name="navigation",
            label="Navigation System Builder",
            build_fn=navigation_builder.build,
            required=True,
        ),
        PipelineStage(
            name="runtime_indexes",
            label="Runtime Index Builder",
            build_fn=runtime_index_builder.build,
            required=True,
        ),
        PipelineStage(
            name="statistics",
            label="Statistics",
            build_fn=statistics.build,
            required=False,
        ),
        PipelineStage(
            name="validation",
            label="Validation",
            build_fn=validation.build,
            required=False,  # Errors recorded in diagnostics; doesn't abort by default
        ),
    ]


# Public API
def get_pipeline_stages() -> List[PipelineStage]:
    """Returns the ordered list of TKB pipeline stages."""
    return _get_stages()
