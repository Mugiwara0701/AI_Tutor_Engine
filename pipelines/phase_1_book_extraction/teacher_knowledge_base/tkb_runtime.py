"""
teacher_knowledge_base/tkb_runtime.py — M6.3 (complete)

TKBRuntime: the read-only Phase 2 API for a sealed TeacherKnowledgeBase.

SPECIFICATION: RUNTIME_API_SPECIFICATION.md v1.1.1 (FROZEN)

PRINCIPLE (spec §1):
  All operations complete in deterministic latency because all indexes are
  pre-built. Phase 2 loads the TKB JSON into memory once per session;
  all APIs are in-memory dict lookups.

  Phase 2 NEVER writes to TKB. TKBRuntime is strictly read-only.

API GROUPS (spec §4–§10):
  §4  Concept APIs         — get_concept, get_concept_by_name, get_concept_by_key
  §5  TeachingUnit APIs    — get_teaching_unit, get_teaching_units,
                              get_teaching_unit_for_section
  §6  Content Retrieval    — get_examples, get_figures, get_tables, get_formulae,
                              get_analogies, get_activities, get_learning_objectives,
                              get_common_mistakes, get_misconceptions,
                              get_applications, get_related_concepts, get_revision_notes
  §7  Learning Path APIs   — get_prerequisites, get_learning_path,
                              get_learning_path_to, get_remediation_path
  §8  Assessment APIs      — get_assessments, get_assessments_batch,
                              get_practice_questions, get_chapter_test,
                              get_diagnostic_items
  §9  Search API           — search (lexical BM25 v1)
  §10 Session APIs         — get_progression_template, get_stage_resources,
                              get_revision_resources, get_tkb_info

ERROR CONTRACT (spec §3):
  - Not found → return None (never raises on missing data)
  - Empty result → return [] (never None for list-returning APIs)
  - Invalid arguments → return None / [] defensively
  - Version mismatch → raises TKBRuntimeError at load time
"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("teacher_knowledge_base.tkb_runtime")

SUPPORTED_SCHEMA_VERSION = "1.1.1"
VALID_LEARNING_STAGES = {
    "BEGINNER", "INTERMEDIATE", "ADVANCED", "MASTERY", "ASSESSMENT_READY",
}
VALID_PATH_STYLES = {
    "canonical", "beginner", "accelerated", "prerequisite_first", "example_first",
}


class TKBRuntimeError(Exception):
    """Raised when TKBRuntime cannot be initialised (e.g. version mismatch)."""


class TKBRuntime:
    """Read-only Phase 2 API over a sealed TeacherKnowledgeBase.

    Load once per session from a TKB dict or TeacherKnowledgeBase artifact:
        runtime = TKBRuntime.from_dict(tkb_dict)
        runtime = TKBRuntime.from_artifact(tkb_artifact)

    All methods follow the error contract in RUNTIME_API_SPECIFICATION §3.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, tkb_dict: Dict[str, Any]) -> None:
        """Initialise from a fully-assembled TKB dict.

        Raises TKBRuntimeError if schema_version is unsupported.
        """
        schema_version = tkb_dict.get("schema_version", "")
        if schema_version and schema_version != SUPPORTED_SCHEMA_VERSION:
            raise TKBRuntimeError(
                f"TKBRuntime: unsupported schema_version {schema_version!r}. "
                f"Expected {SUPPORTED_SCHEMA_VERSION!r}."
            )

        self._tkb: Dict[str, Any] = tkb_dict

        # Pre-cache the top-level sections for O(1) access.
        self._teaching_units: Dict[str, Any] = tkb_dict.get("teaching_units") or {}
        self._ri: Dict[str, Any] = tkb_dict.get("runtime_indexes") or {}
        self._nav: Dict[str, Any] = tkb_dict.get("navigation") or {}
        self._edg: Dict[str, Any] = tkb_dict.get("enriched_dependency_graph") or {}
        self._cpts: Dict[str, Any] = tkb_dict.get("concept_progression_templates") or {}
        self._metadata: Dict[str, Any] = tkb_dict.get("metadata") or {}

        # Runtime-index sub-sections
        self._cli: Dict[str, Any] = self._ri.get("concept_lookup_index") or {}
        self._cli_by_id: Dict[str, Any] = self._cli.get("by_id") or {}
        self._cli_by_key: Dict[str, str] = self._cli.get("by_key") or {}
        self._cli_by_name: Dict[str, str] = self._cli.get("by_name") or {}
        self._ssi: Dict[str, Any] = self._ri.get("semantic_search_index") or {}
        self._ssi_entries: List[Dict[str, Any]] = self._ssi.get("entries") or []
        self._prereq_idx: Dict[str, Any] = (
            self._ri.get("prerequisite_index") or {}
        ).get("by_concept") or {}
        self._teach_idx: Dict[str, Any] = self._ri.get("teaching_retrieval_index") or {}
        self._assess_idx: Dict[str, Any] = self._ri.get("assessment_retrieval_index") or {}
        self._ail: Dict[str, Any] = self._assess_idx.get("assessment_item_location") or {}
        self._rev_idx: Dict[str, Any] = self._ri.get("revision_retrieval_index") or {}

        # Navigation sub-sections
        self._lpn: Dict[str, Any] = self._nav.get("learning_path_navigation") or {}

        logger.info(
            "TKBRuntime: loaded tkb_id=%s schema=%s concepts=%d",
            tkb_dict.get("tkb_id", "?"),
            schema_version or "?",
            len(self._teaching_units),
        )

    @classmethod
    def from_dict(cls, tkb_dict: Dict[str, Any]) -> "TKBRuntime":
        """Construct from a raw TKB dict (e.g. loaded from JSON)."""
        return cls(tkb_dict)

    @classmethod
    def from_artifact(cls, artifact: Any) -> "TKBRuntime":
        """Construct from a TeacherKnowledgeBase dataclass artifact."""
        return cls(artifact.to_dict())

    @classmethod
    def from_json_str(cls, json_str: str) -> "TKBRuntime":
        """Construct from a JSON string (e.g. read from storage)."""
        import json
        return cls(json.loads(json_str))

    # ------------------------------------------------------------------
    # §4 CONCEPT APIs
    # ------------------------------------------------------------------

    def get_concept(self, concept_id: str) -> Optional[Dict[str, Any]]:
        """O(1) concept lookup by concept_id.

        Returns ConceptNavEntry or None if not found (spec §4).
        """
        if not concept_id:
            return None
        return self._cli_by_id.get(concept_id)

    def get_concept_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """O(1) lookup by human-readable name (case-insensitive).

        Returns ConceptNavEntry or None (spec §4).
        """
        if not name:
            return None
        cid = self._cli_by_name.get(name.lower())
        if not cid:
            return None
        return self._cli_by_id.get(cid)

    def get_concept_by_key(self, concept_key: str) -> Optional[Dict[str, Any]]:
        """O(1) lookup by compiler canonical key.

        Returns ConceptNavEntry or None (spec §4).
        """
        if not concept_key:
            return None
        cid = self._cli_by_key.get(concept_key)
        if not cid:
            return None
        return self._cli_by_id.get(cid)

    # ------------------------------------------------------------------
    # §5 TEACHING UNIT APIs
    # ------------------------------------------------------------------

    def get_teaching_unit(self, concept_id: str) -> Optional[Dict[str, Any]]:
        """O(1) TeachingUnit retrieval by concept_id.

        Returns TeachingUnit dict or None (spec §5).
        """
        if not concept_id:
            return None
        return self._teaching_units.get(concept_id)

    def get_teaching_units(
        self, concept_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Batch TeachingUnit retrieval. Returns dict concept_id → TU | None.

        Supports up to 50 IDs per call (spec §5 performance contract).
        """
        return {cid: self._teaching_units.get(cid) for cid in (concept_ids or [])}

    def get_teaching_unit_for_section(
        self, edst_node_id: str
    ) -> List[Dict[str, Any]]:
        """All TeachingUnits in a given EDST section.

        Returns list of TeachingUnit dicts (may be empty) (spec §5).
        """
        if not edst_node_id:
            return []
        by_section: Dict[str, List[str]] = (
            self._teach_idx.get("by_section_id") or {}
        )
        cids: List[str] = by_section.get(edst_node_id) or []
        return [
            tu for cid in cids
            if (tu := self._teaching_units.get(cid)) is not None
        ]

    # ------------------------------------------------------------------
    # §6 CONTENT RETRIEVAL APIs
    # ------------------------------------------------------------------

    def get_examples(
        self, concept_id: str, worked_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Examples for a concept. worked_only=True returns only worked examples.

        Returns list of ExampleItem dicts (spec §6).
        """
        tu = self._teaching_units.get(concept_id)
        if tu is None:
            return []
        if worked_only:
            return list(tu.get("worked_examples") or [])
        return list((tu.get("examples") or []) + (tu.get("worked_examples") or []))

    def get_figures(
        self,
        concept_id: Optional[str] = None,
        section_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Figures for a concept or EDST section.

        Returns list of FigureRef dicts (spec §6).
        """
        if concept_id:
            tu = self._teaching_units.get(concept_id)
            return list(tu.get("figures") or []) if tu else []
        if section_id:
            # Get all TUs in the section, collect their figures
            tus = self.get_teaching_unit_for_section(section_id)
            seen: set = set()
            result: List[Dict[str, Any]] = []
            for tu in tus:
                for fig in (tu.get("figures") or []):
                    fid = fig.get("figure_id", "")
                    if fid and fid not in seen:
                        seen.add(fid)
                        result.append(fig)
            return result
        return []

    def get_tables(self, concept_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Tables for a concept.

        Returns list of TableRef dicts (identical schema to FigureRef — spec §9b).
        """
        if not concept_id:
            return []
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("tables") or []) if tu else []

    def get_formulae(self, concept_id: str) -> List[Dict[str, Any]]:
        """Formulae for a concept. Returns list of FormulaItem dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("formulae") or []) if tu else []

    def get_analogies(self, concept_id: str) -> List[Dict[str, Any]]:
        """Analogies for a concept. Returns list of Analogy dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("analogies") or []) if tu else []

    def get_activities(self, concept_id: str) -> List[Dict[str, Any]]:
        """Activities for a concept. Returns list of ActivityItem dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("activities") or []) if tu else []

    def get_learning_objectives(
        self,
        concept_id: str,
        bloom_level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Learning objectives for a concept. Optionally filter by bloom_level.

        Returns list of LearningObjective dicts (spec §6).
        """
        tu = self._teaching_units.get(concept_id)
        if tu is None:
            return []
        objs: List[Dict[str, Any]] = list(tu.get("learning_objectives") or [])
        if bloom_level:
            objs = [o for o in objs if o.get("bloom_level") == bloom_level]
        return objs

    def get_common_mistakes(self, concept_id: str) -> List[Dict[str, Any]]:
        """Common mistakes for a concept. Returns list of CommonMistake dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("common_mistakes") or []) if tu else []

    def get_misconceptions(self, concept_id: str) -> List[Dict[str, Any]]:
        """Misconceptions for a concept. Returns list of MisconceptionRef dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("misconceptions") or []) if tu else []

    def get_applications(self, concept_id: str) -> List[Dict[str, Any]]:
        """Real-world applications of a concept. Returns list of ApplicationRef dicts (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("applications") or []) if tu else []

    def get_related_concepts(self, concept_id: str) -> List[Dict[str, Any]]:
        """Related concepts (derived from EKG RELATED_TO). Returns list of ConceptRef (spec §6)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("related_concepts") or []) if tu else []

    def get_revision_notes(
        self, concept_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Revision notes for a concept, or all notes in learning order.

        If concept_id is None, aggregates all revision notes in EDG topological
        order (spec §6).
        """
        if concept_id:
            tu = self._teaching_units.get(concept_id)
            return list(tu.get("revision_notes") or []) if tu else []
        # All notes in topological order
        topo: List[str] = self._edg.get("topological_order") or list(
            self._teaching_units.keys()
        )
        result: List[Dict[str, Any]] = []
        seen: set = set()
        for cid in topo:
            tu = self._teaching_units.get(cid)
            if tu is None:
                continue
            for note in (tu.get("revision_notes") or []):
                nid = note.get("note_id", "")
                if nid and nid not in seen:
                    seen.add(nid)
                    result.append(note)
        return result

    # ------------------------------------------------------------------
    # §7 LEARNING PATH APIs
    # ------------------------------------------------------------------

    def get_prerequisites(
        self,
        concept_id: str,
        blocking_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Prerequisites for a concept.

        Returns list of ConceptNavEntry dicts; blocking_only=True filters to
        REQUIRES edges only (spec §7).
        """
        entry = self._prereq_idx.get(concept_id) or {}
        if blocking_only:
            ids: List[str] = entry.get("blocking_prerequisite_ids") or []
        else:
            ids = list(
                (entry.get("blocking_prerequisite_ids") or []) +
                (entry.get("soft_prerequisite_ids") or [])
            )
        return [
            nav for cid in ids
            if (nav := self._cli_by_id.get(cid)) is not None
        ]

    def get_learning_path(
        self, style: str = "canonical"
    ) -> List[Dict[str, Any]]:
        """Ordered learning path.

        style: "canonical"|"beginner"|"accelerated"|"prerequisite_first"|"example_first"
        Returns list of ConceptNavEntry dicts in learning order (spec §7).
        """
        if style not in VALID_PATH_STYLES:
            return []
        key = f"{style}_path"
        cids: List[str] = self._lpn.get(key) or []
        return [
            nav for cid in cids
            if (nav := self._cli_by_id.get(cid)) is not None
        ]

    def get_learning_path_to(
        self, goal_concept_id: str
    ) -> Optional[Dict[str, Any]]:
        """Prerequisite chain leading to a goal concept.

        Returns PrerequisiteChain dict or None if no chain exists (spec §7).
        """
        chains: List[Dict[str, Any]] = self._edg.get("prerequisite_chains") or []
        for chain in chains:
            if chain.get("root_concept_id") == goal_concept_id:
                return chain
        return None

    def get_remediation_path(
        self, failed_concept_id: str
    ) -> Optional[Dict[str, Any]]:
        """Remediation path for a concept the student struggled with.

        When multiple paths exist, returns the one with minimum total_minutes;
        tie-break: lowest concept_id alphabetically in path[0] (spec §7).
        """
        paths: List[Dict[str, Any]] = self._edg.get("remediation_paths") or []
        candidates = [
            p for p in paths if p.get("trigger_concept_id") == failed_concept_id
        ]
        if not candidates:
            return None
        # Sort by total_minutes asc, then path[0] concept_id asc (deterministic)
        candidates.sort(key=lambda p: (
            float(p.get("total_minutes") or 0),
            (p.get("path") or [""])[0],
        ))
        return candidates[0]

    # ------------------------------------------------------------------
    # §8 ASSESSMENT APIs
    # ------------------------------------------------------------------

    def _resolve_item(
        self, item_id: str
    ) -> Optional[Dict[str, Any]]:
        """Resolve an assessment item_id to its full AssessmentItem dict."""
        loc = self._ail.get(item_id)
        if not loc:
            return None
        cid = loc.get("concept_id", "")
        is_practice = bool(loc.get("is_practice"))
        tu = self._teaching_units.get(cid)
        if tu is None:
            return None
        items = tu.get("practice_questions" if is_practice else "assessments") or []
        for item in items:
            if item.get("item_id") == item_id:
                return item
        return None

    def get_assessments(
        self,
        concept_id: str,
        difficulty: Optional[str] = None,
        bloom_level: Optional[str] = None,
        provenance_tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Assessment items for a concept with optional filters (spec §8)."""
        by_concept: Dict[str, List[str]] = self._assess_idx.get("by_concept_id") or {}
        item_ids: List[str] = by_concept.get(concept_id) or []
        result: List[Dict[str, Any]] = []
        for iid in item_ids:
            item = self._resolve_item(iid)
            if item is None:
                continue
            if difficulty and item.get("difficulty") != difficulty:
                continue
            if bloom_level and item.get("bloom_level") != bloom_level:
                continue
            if provenance_tier and item.get("provenance_tier") != provenance_tier:
                continue
            result.append(item)
        return result

    def get_assessments_batch(
        self, concept_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch assessment retrieval. Returns dict concept_id → items (spec §8)."""
        return {cid: self.get_assessments(cid) for cid in (concept_ids or [])}

    def get_practice_questions(self, concept_id: str) -> List[Dict[str, Any]]:
        """Practice questions for a concept (spec §8)."""
        tu = self._teaching_units.get(concept_id)
        return list(tu.get("practice_questions") or []) if tu else []

    def get_chapter_test(self) -> List[str]:
        """Ordered list of item_ids for the curated chapter test (spec §8).

        Caller resolves each item via get_assessments() or _resolve_item().
        """
        return list(self._assess_idx.get("chapter_test_item_ids") or [])

    def get_diagnostic_items(self, concept_id: str) -> List[Dict[str, Any]]:
        """Diagnostic assessment items for prerequisite concepts of concept_id.

        Returns items from prerequisite concepts to check readiness (spec §8).
        """
        prereq_navs = self.get_prerequisites(concept_id, blocking_only=True)
        result: List[Dict[str, Any]] = []
        seen_ids: set = set()
        for nav in prereq_navs:
            prereq_cid = nav.get("concept_id", "")
            for item in self.get_assessments(prereq_cid):
                iid = item.get("item_id", "")
                if iid and iid not in seen_ids:
                    seen_ids.add(iid)
                    result.append(item)
        return result

    # ------------------------------------------------------------------
    # §9 SEARCH API (V1: LEXICAL / BM25)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Lexical search over SemanticSearchIndex.display_text (spec §9).

        V1: simple token-overlap scoring (BM25-compatible token matching).
        Filters: content_types, difficulty, bloom_level, section_id, importance,
                 max_results (default 10, max 50).

        Returns SearchResult dict with results list and total_found.
        """
        filters = filters or {}
        max_results: int = min(int(filters.get("max_results") or 10), 50)
        content_types: Optional[List[str]] = filters.get("content_types")
        difficulty_filter: Optional[str] = filters.get("difficulty")
        bloom_filter: Optional[str] = filters.get("bloom_level")
        importance_filter: Optional[str] = filters.get("importance")

        if not query or not query.strip():
            return {
                "query": query,
                "search_type": "lexical_v1",
                "results": [],
                "total_found": 0,
            }

        query_tokens = set(_tokenize(query))
        scored: List[Dict[str, Any]] = []

        for entry in self._ssi_entries:
            # Content-type filter (pre-BM25)
            if content_types and entry.get("entry_type") not in content_types:
                continue

            # Concept-level metadata filters
            concept_ids_in_entry: List[str] = entry.get("concept_ids") or []
            if difficulty_filter or importance_filter:
                match = False
                for cid in concept_ids_in_entry:
                    tu = self._teaching_units.get(cid) or {}
                    if difficulty_filter and tu.get("difficulty") != difficulty_filter:
                        continue
                    if importance_filter and tu.get("importance") != importance_filter:
                        continue
                    match = True
                    break
                if not match and concept_ids_in_entry:
                    continue

            # bloom_level filter (applies to objectives; skip non-concept entries)
            if bloom_filter:
                if entry.get("entry_type") not in ("concept", "definition"):
                    continue  # bloom filter only relevant for concept entries

            # BM25-compatible token overlap scoring
            display_text: str = entry.get("display_text") or ""
            entry_tokens = set(_tokenize(display_text))
            if not entry_tokens:
                continue
            overlap = len(query_tokens & entry_tokens)
            if overlap == 0:
                continue
            # Normalised score: overlap / max(query_len, entry_len) → [0, 1]
            score = round(overlap / max(len(query_tokens), len(entry_tokens)), 4)
            scored.append({
                "entry_id": entry.get("entry_id", ""),
                "entry_type": entry.get("entry_type", ""),
                "display_text": display_text,
                "concept_ids": concept_ids_in_entry,
                "unit_id": entry.get("unit_id", ""),
                "score": score,
            })

        # Sort by score descending, then entry_id ascending (deterministic tie-break)
        scored.sort(key=lambda x: (-x["score"], x["entry_id"]))
        top = scored[:max_results]

        return {
            "query": query,
            "search_type": "lexical_v1",
            "results": top,
            "total_found": len(scored),
        }

    # ------------------------------------------------------------------
    # §10 SESSION APIs
    # ------------------------------------------------------------------

    def get_progression_template(
        self, concept_id: str
    ) -> Optional[Dict[str, Any]]:
        """ConceptProgressionTemplate for a concept (spec §10)."""
        return self._cpts.get(concept_id)

    def get_stage_resources(
        self, concept_id: str, stage: str
    ) -> Optional[Dict[str, Any]]:
        """Stage-specific resource IDs for a concept and learning stage.

        stage must be one of BEGINNER, INTERMEDIATE, ADVANCED, MASTERY,
        ASSESSMENT_READY. Returns StageResourceSet dict or None (spec §10).
        """
        if stage not in VALID_LEARNING_STAGES:
            return None
        cpt = self._cpts.get(concept_id)
        if cpt is None:
            return None
        return (cpt.get("stage_resources") or {}).get(stage)

    def get_revision_resources(
        self, concept_id: str
    ) -> Optional[Dict[str, Any]]:
        """Revision resource IDs for a concept.

        Returns RevisionResourceSet dict or None (spec §10).
        """
        cpt = self._cpts.get(concept_id)
        if cpt is None:
            return None
        return cpt.get("revision_resources")

    def get_tkb_info(self) -> Dict[str, Any]:
        """TKBInfo: summary metadata about this TKB (spec §10).

        Returns TKBInfo dict:
          {tkb_id, schema_version, tkb_scope, chapter_title,
           chapter_number, status, builder_version, total_concepts}
        """
        return {
            "tkb_id": self._tkb.get("tkb_id", ""),
            "schema_version": self._tkb.get("schema_version", ""),
            "tkb_scope": self._metadata.get("tkb_scope", "chapter"),
            "chapter_title": self._metadata.get("chapter_title", ""),
            "chapter_number": int(self._metadata.get("chapter_number") or 0),
            "status": self._metadata.get("status", ""),
            "builder_version": self._metadata.get("builder_version", ""),
            "total_concepts": len(self._teaching_units),
        }

    # ------------------------------------------------------------------
    # Performance-contract helpers (spec §11)
    # ------------------------------------------------------------------

    def concept_count(self) -> int:
        """Total number of concepts in this TKB."""
        return len(self._teaching_units)

    def is_loaded(self) -> bool:
        """True once the TKBRuntime has been successfully initialised."""
        return bool(self._tkb)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Simple whitespace/punctuation tokeniser for BM25 token matching.

    Lowercases and splits on non-alphanumeric characters.
    """
    return _TOKEN_RE.findall(text.lower())
