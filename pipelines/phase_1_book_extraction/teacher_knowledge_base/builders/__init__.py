"""
teacher_knowledge_base/builders/ — M6.1: individual stage builder modules.

Each module implements one stage of the TKB build pipeline and exports a
single build(context: TKBContext) -> None function. Modules are imported
lazily by pipeline.py to avoid circular imports at package load time.

Stage modules:
  edst_builder.py           — Enriched Document Structure Tree
  edg_builder.py            — Enriched Dependency Graph
  ekg_builder.py            — Enriched Knowledge Graph
  teaching_unit_builder.py  — Teaching Units
  progression_builder.py    — Concept Progression Templates
  curriculum_builder.py     — Curriculum Graph
  navigation_builder.py     — Navigation System
  runtime_index_builder.py  — Runtime Indexes
"""
