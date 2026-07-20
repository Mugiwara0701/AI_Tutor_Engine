"""
teacher_knowledge_base/pipeline.py — M6.1/M6.2 (remediated)

Pipeline stage ordering matches M6_ARCHITECTURE_SPECIFICATION.md §6:
  T1: EDST Construction
  T2: EDG Construction
  T3: TeachingUnit Assembly
  T4: ConceptProgressionTemplate Build
  T5: EKG Construction
  T6: CurriculumGraph
  T7: Runtime Index Build
  T8: NavigationIndex Build
  T9: Validation Pass
  T10: Serialization & Sealing

NOTE: In our pipeline, we build TU (T3) first so that EDST (T1), EDG (T2),
EKG (T5) can all read from TU content. The spec's T-numbering describes
logical data dependencies, not strict sequential execution order.

Our execution order:
  1. teaching_units  (T3 — built first, feeds all graph enrichment)
  2. edg             (T2 — needs concept_index, feeds topological_order)
  3. edst            (T1 — needs TU for counts and aggregates)
  4. concept_progression_templates (T4 — needs TU + EDG)
  5. ekg             (T5 — needs TU content for edge derivation)
  6. curriculum_graph (T6 — needs TU + EDG topological_order)
  7. runtime_indexes (T7 — needs TU + EDG + EDST + CG + Nav)
  8. navigation      (T8 — needs TU + EDG + EDST + CPT + CG)
  9. statistics      (T9a — needs all above)
  10. validation     (T9b — needs all above)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class PipelineStage:
    name: str
    label: str
    build_fn: Callable
    required: bool = True


def get_pipeline_stages() -> List[PipelineStage]:
    from .builders import (
        edst_builder, edg_builder, ekg_builder,
        teaching_unit_builder, progression_builder,
        curriculum_builder, navigation_builder, runtime_index_builder,
    )
    from . import statistics, validation

    return [
        PipelineStage("teaching_units", "TeachingUnit Assembly (T3)",
                      teaching_unit_builder.build, required=True),
        PipelineStage("edg", "EDG Construction (T2)",
                      edg_builder.build, required=True),
        PipelineStage("edst", "EDST Construction (T1)",
                      edst_builder.build, required=True),
        PipelineStage("concept_progression_templates", "CPT Build (T4)",
                      progression_builder.build, required=True),
        PipelineStage("ekg", "EKG Construction (T5)",
                      ekg_builder.build, required=False),
        PipelineStage("curriculum_graph", "CurriculumGraph (T6)",
                      curriculum_builder.build, required=False),
        PipelineStage("navigation", "NavigationIndex Build (T8)",
                      navigation_builder.build, required=True),
        PipelineStage("runtime_indexes", "Runtime Index Build (T7)",
                      runtime_index_builder.build, required=True),
        PipelineStage("statistics", "Statistics",
                      statistics.build, required=False),
        PipelineStage("validation", "Validation Pass (T9)",
                      validation.build, required=False),
    ]
