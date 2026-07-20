"""
pipeline.py — Phase 1 orchestrator.

    NCERT PDF -> chapter split -> OCR -> layout detection (geometric only)
              -> Python deterministic extraction (content blocks, topics)
              -> Stage A: Geometry Segmentation      (WHERE — no VLM)
              -> Stage B: Block Classification       (WHAT  — no VLM)
              -> Stage C: Priority Assignment        (HOW IMPORTANT)
              -> Qwen2.5-VL-3B semantics (topics/figures/tables/chapter
                          metadata; equations ONLY for regions Stage B
                          classified as introducing reusable knowledge —
                          see modules/equation_intent.py, ISSUE 3/4)
              -> Stage D: Scoped Educational Extraction (hybrid
                          deterministic-template-first, VLM fallback;
                          reuses the SAME equation-semantics result via
                          semantic_processor's per-chapter cache instead
                          of re-calling the VLM — see ISSUE 1)
              -> Stage E: Educational Validation      (deterministic only)
              -> merge -> validate -> one Master Chapter JSON

DUPLICATE-EQUATION-ANALYSIS FIX (ISSUE 1, see also equation_intent.py and
semantic_processor.py's equation-semantics cache): Stage A/B/C now run
BEFORE the flat top-level `equations` list is built (they used to run
after). Previously that flat list called
semantic_processor.process_equation_semantics() unconditionally for EVERY
layout-detected equation region, regardless of what Stage B would later
classify it as -- and Stage D's FormulaFamilyRecognizer could independently
call the exact same function for the exact same region once it had been
classified as Formula Box/Law, producing two VLM calls for one physical
equation (visible in logs as "Stage A/B/C ... then equation_analysis runs
again"). Reordering lets the flat list consult Stage B's classification via
equation_intent.introduces_reusable_knowledge() up front, and the
per-chapter cache in semantic_processor.py is the backstop that guarantees
no duplicate VLM call even if Stage D asks about the same region again.

REGRESSION-FIX NOTE (see REGRESSION_AUDIT.md): an earlier revision of this
file replaced the topics/concepts/glossary/figures/tables/equations/.../
learning_graph/concept_graph/semantic_index/ai_metadata/generation_metadata
build-out with ONLY the Stage A-E block/educational-object pipeline,
labeling the former "Phase 2" and shipping no Phase 2 entry point at all --
so every one of those capabilities silently disappeared from the pipeline's
actual output even though the code that builds them
(modules/graph_builder.py, modules/content_blocks.py,
modules/semantic_processor.py's topic/chapter-metadata runners,
json_writer.assemble_chapter_json) was left intact and unused. This
revision restores every one of those calls IN ADDITION TO the Stage A-E
block/educational-object pipeline (kept, unchanged in behavior) and folds
both into a single Master JSON per chapter via
json_writer.assemble_chapter_json/write_chapter_json.

Run:
    python pipeline.py                     # process every PDF in pdf_in/
    python pipeline.py --no-vlm            # deterministic-only dry run (no model load)
    python pipeline.py --force             # ignore resumable cache, re-extract everything
    python pipeline.py --batch-size 8

The model (Qwen2.5-VL-3B-Instruct) is loaded once via vlm_inference.get_model()
on the first call that needs it and reused for the rest of the run.
"""
import functools
import os
import sys
import time
import glob
import logging
from datetime import datetime, timezone
import argparse
from typing import Optional, List, Dict, Any, Tuple, Callable

import fitz  # PyMuPDF

from config import (PDF_INPUT_FOLDER, DEFAULT_PAGE_BATCH_SIZE,
                     VLM_MODEL_ID, DEFAULT_SUBJECT, DEFAULT_CLASS)
from modules import pdf_parser, layout_detector, ocr_engine, content_blocks, language_detector
from modules import semantic_processor, graph_builder, json_writer, vlm_inference
from modules import stage_a_geometry, stage_b_classify, stage_c_priority, stage_d_extraction, stage_e_validation
from modules import kg_readiness
from modules import equation_intent
from modules import canonical
from modules import topic_linker
from modules.pdf_parser import make_id, slugify, auto_detect_subject, auto_detect_class
from compiler.registries import create_registry_manager, populate_registries
from compiler.enrichment import enrich_registries
from compiler.normalization import normalize_registries, canonical_lookup_key
from compiler.references import resolve_references
from compiler.relationships import resolve_relationships
from compiler.validation import validate_compiler_state
from compiler.build import generate_compiler_manifest, generate_compiler_statistics
from compiler.fingerprints import generate_compiler_fingerprints
from compiler.finalize import finalize_compiler_build
from compiler import state as compiler_state
from knowledge_graph.build_nodes import build_knowledge_graph_nodes
from knowledge_graph.build_edges import build_knowledge_graph_edges
from knowledge_graph.validation import validate_knowledge_graph
from knowledge_graph.build import generate_knowledge_graph_manifest, generate_knowledge_graph_statistics
from knowledge_graph.fingerprints import generate_graph_fingerprints
from knowledge_graph.finalize import finalize_knowledge_graph
from knowledge_graph.identity import graph_id as kg_graph_id, graph_urn as kg_graph_urn
from knowledge_graph.schema import KnowledgeGraph, KnowledgeGraphMetadata
from knowledge_graph import state as kg_state
# ---- Milestone 5.1: Document Structure Tree (DST) — Pipeline Integration -
# document_structure_tree/ is DST's counterpart to knowledge_graph/ above
# (see that package's own __init__.py: "both are built from the same
# upstream inputs (Chapter JSON, canonical registries) ... neither package
# imports from the other"). Milestones 1-4 (models, builder, validation
# engine, artifact generation) and the Milestone 5 scaffolding (state.py,
# registry_snapshot.py, persistence.py) already exist in that package,
# frozen and unmodified by this milestone -- see its own __init__.py for
# the exact boundary. This milestone (M5.1) imports only what is needed to
# INVOKE that existing, frozen machinery from the pipeline: the builder
# adapter, artifact generation (which itself drives the frozen validation
# engine -- see artifact.py's own docstring), the DST exception hierarchy
# (so a build/artifact failure can be logged with a precise cause before
# it propagates), the chapter-scoped "current DST" state slot, and the
# canonical-registry adapter over this pipeline's own already-populated
# `registry_manager`. persistence.py is deliberately NOT imported here:
# artifact registration, persistence, and build-metadata changes are out
# of scope for this milestone (see this milestone's own "Do NOT
# implement" instructions) -- exactly as document_structure_tree's own
# __init__.py already keeps persist_document_structure_tree() out of the
# package's own import surface for the analogous reason.
from document_structure_tree.builder import build_tree_from_chapter_json
from document_structure_tree.artifact import generate_artifact
from document_structure_tree.exceptions import (
    DocumentStructureTreeError,
    DSTArtifactError,
    DSTBuildError,
    DSTIdentityError,
    DSTSerializationError,
    DSTValueError,
)
from document_structure_tree.primitives import ChapterId, CompilerVersion, SchemaVersion
from document_structure_tree.registry_snapshot import CompilerRegistrySnapshot
from document_structure_tree.enums import ValidationStatus as DSTValidationStatus
from document_structure_tree import state as dst_state
from schemas.chapter_schema import ChapterJSON
from validation.system_integrity import validate_system_integrity
from validation import state as system_integrity_state
from validation.determinism import validate_determinism
from validation import determinism_state
from validation.release import finalize_release
from validation import release_state
from build_metadata.build import finalize_build_metadata
from build_metadata import state as build_metadata_state
from dependency_graph.build import generate_dependency_graph
from dependency_graph import state as dependency_graph_state
from change_detection.engine import detect_changes
from change_detection import state as change_detection_state
from incremental_compilation.engine import plan_incremental_compilation
from incremental_compilation import state as incremental_compilation_state
from incremental_compilation_validation.engine import validate_incremental_compilation
from incremental_compilation_validation import state as incremental_compilation_validation_state
from incremental_compilation_finalization.finalize import finalize_incremental_compilation
from incremental_compilation_finalization import state as incremental_compilation_finalization_state
from build_executor.executor import execute_chapter as _f3_execute_chapter
from build_executor.plan import generate_execution_plan as _f3_generate_execution_plan

# ---- Phase 1 Output Persistence Enhancement ------------------------------
# Additive-only: persists chapter-scoped Phase 1 artifacts that already
# exist (Compiler IR registries/metadata, the Knowledge Graph, the Build
# Dependency Graph, Stage D validation, Build Metadata) but previously
# lived only in each package's own state.py module-level slots. See each
# module's own docstring for exactly what it persists and why. Wired in
# at the single call site near the end of process_chapter(), after
# json_writer.write_chapter_json() -- never before it, never changing
# Stage A-E's own call order above.
from compiler.persistence import persist_registries, persist_compiler_metadata
from knowledge_graph.persistence import persist_knowledge_graph
from dependency_graph.persistence import persist_dependency_graph
from validation.persistence import persist_validation_record
from modules import copyright_sanitizer
from extraction_debug.persistence import persist_extraction_debug
from build_metadata.persistence import persist_build_metadata as _persist_build_metadata_record
# ---- Milestone 5.2: Document Structure Tree (DST) — Artifact
# Registration & Persistence -------------------------------------------
# Additive-only, mirroring the block immediately above one artifact type
# over: `persist_document_structure_tree()` is Milestone 5's own
# persistence.py (document_structure_tree/persistence.py, frozen,
# unmodified by this milestone -- see that module's own docstring),
# deliberately NOT imported by document_structure_tree/__init__.py for
# the same reason knowledge_graph.persistence isn't imported by
# knowledge_graph/__init__.py either (see that package's own docstring).
# `generate_dst_metadata`/`attach_dst_metadata` are this milestone's own
# additions to build_metadata/build.py -- see that module's own
# docstring for why `attach_dst_metadata()` exists as a separate,
# post-hoc call rather than a new `finalize_build_metadata()` argument
# used at its original call site (the DST does not exist yet at that
# point in process_chapter()).
from document_structure_tree.persistence import persist_document_structure_tree
from build_metadata.build import generate_dst_metadata, attach_dst_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ncert_pipeline")

# ---- Milestone 5.1: DST artifact-metadata version markers ---------------
# `schema_version`/`compiler_version` (schema §2.1/§2.3) must be
# independently settable semver strings (document_structure_tree.primitives.
# SchemaVersion/CompilerVersion both enforce MAJOR.MINOR.PATCH) -- neither
# may be inferred from the other, or from this compiler's own
# COMPILER_VERSION (compiler/build.py: "B5.1", a milestone-name string, not
# semver -- see that module's own constants block). DST_SCHEMA_VERSION
# mirrors the schema-version token every existing DST fixture/usage example
# already builds artifacts against (document_structure_tree/__init__.py's
# own usage example, tests/fixtures.py); DST_COMPILER_VERSION is this
# pipeline's own DST-integration version marker (bump only when this
# milestone's own pipeline-wiring shape changes in a way a consumer of
# `artifact_metadata.compiler_version` should be able to detect -- same
# convention as compiler/build.py's own BUILD_VERSION).
DST_SCHEMA_VERSION = SchemaVersion("1.1.0")
DST_COMPILER_VERSION = CompilerVersion("1.0.0")


def _topic_lookup_factory(structure):
    """Returns a page -> topic_id lookup used by definitions/examples/boxes
    to attach themselves to the enclosing topic."""
    def lookup(page: int) -> Optional[str]:
        candidates = [t for t in structure.topics if t.page_start <= page <= t.page_end]
        return candidates[-1].id if candidates else None
    return lookup


def _region_to_id(kind: str, chapter_title: str, region, idx: int) -> str:
    return make_id(chapter_title, kind, str(region.page), str(idx))


def _recover_script_mismatched_text(doc: fitz.Document, structure: pdf_parser.ChapterStructure,
                                     ocr_text_by_page: Dict[int, str], extraction_logs: Dict[str, Any]) -> None:
    """Fixes chapter_title/heading text that pdf_parser's deterministic
    font-based detection pulled from a script-mismatched text layer -- e.g.
    a Hindi/Sanskrit NCERT PDF typeset in a legacy non-Unicode font (Kruti
    Dev, DevLys, ...) whose text layer decodes to Latin-looking gibberish
    instead of real Devanagari (see modules/language_detector.py for the
    full explanation). ocr_engine already detects this per-page and falls
    back to Tesseract for body-text OCR confidence, but that recovered text
    was never fed back into structure.chapter_title / structure.topics[].title
    themselves -- this is what closes that gap, via the recover_chapter_title
    / recover_heading VLM tasks that exist for exactly this. Mutates
    `structure` in place; logs every change (or recovery miss) into
    extraction_logs so it's visible in the final JSON, never silent.

    Uses a lower min_alpha_chars than is_text_usable_for_language's default
    (15) for every check here: that default is tuned for ocr_engine.py's
    page-level text, where it protects short/mostly-numeric lines from
    triggering unnecessary OCR. A chapter title or heading is a short string
    by nature (often under 15 letters even in full), so the page-level
    default would silently wave through exactly the garbled short titles
    this function exists to catch -- as it did for e.g. a 10-letter garbled
    title in real testing."""
    lang = structure.language
    min_alpha = 4  # short-string threshold; see docstring above

    def _usable(text: str) -> bool:
        return language_detector.is_text_usable_for_language(text, lang, min_alpha_chars=min_alpha)

    if structure.chapter_title != "untitled-chapter" and not _usable(structure.chapter_title):
        page_hint = min(1, max(structure.num_pages - 1, 0))
        ocr_text = "\n".join(ocr_text_by_page.get(p, "") for p in (0, 1) if ocr_text_by_page.get(p))[:2000]
        recovered = semantic_processor.process_recover_chapter_title(
            doc, page_hint, structure.chapter_title, structure.book_title, structure.subject, ocr_text)
        new_title = recovered.get("chapter_title")
        if new_title and _usable(str(new_title)):
            logger.info("Recovered chapter title from script-mismatched text layer: %r -> %r",
                        structure.chapter_title, new_title)
            extraction_logs["warnings"].append(
                f"chapter_title recovered via VLM (text layer didn't match '{lang}' script): "
                f"{structure.chapter_title!r} -> {new_title!r}")
            structure.chapter_title = str(new_title)
        else:
            extraction_logs["warnings"].append(
                f"chapter_title text layer didn't match '{lang}' script and VLM recovery did not return "
                f"usable text — keeping the original (possibly garbled) title")

    for t in structure.topics:
        if _usable(t.title):
            continue
        nearby = [o.title for o in structure.topics if o is not t and _usable(o.title)][:3]
        ocr_text_region = ocr_text_by_page.get(t.page_start, "")[:1500]
        recovered = semantic_processor.process_recover_heading(
            doc, t.page_start, t.bbox, t.level, ocr_text_region, nearby, structure.chapter_title)
        new_title = recovered.get("heading_title")
        if new_title and _usable(str(new_title)):
            logger.info("Recovered heading from script-mismatched text layer: %r -> %r", t.title, new_title)
            extraction_logs["warnings"].append(
                f"heading on page {t.page_start} recovered via VLM (text layer didn't match '{lang}' script): "
                f"{t.title!r} -> {new_title!r}")
            t.title = str(new_title)
            new_numbering = recovered.get("numbering")
            if new_numbering:
                t.numbering = str(new_numbering)
        else:
            extraction_logs["warnings"].append(
                f"heading on page {t.page_start} text layer didn't match '{lang}' script and VLM recovery did "
                f"not return usable text — keeping the original (possibly garbled) title")


def _persist_phase1_artifacts(
    *,
    klass: str, subject: str, book_slug: str, chapter_number, chapter_title: str,
    output_root: Optional[str],
    registry_manager,
    compiler_manifest: Dict[str, Any], compiler_statistics: Dict[str, Any],
    compiler_registry_fingerprints: Dict[str, str], compiler_fingerprint: str,
    compiler_validation_report: Dict[str, Any], compiler_readiness_report: Dict[str, Any],
    compiler_build_summary: Dict[str, Any], final_compiler_status: str,
    knowledge_graph_metadata, knowledge_graph_registry_manager,
    knowledge_graph_manifest: Dict[str, Any], knowledge_graph_statistics: Dict[str, Any],
    knowledge_graph_validation_report: Dict[str, Any],
    knowledge_graph_registry_fingerprints: Dict[str, str], knowledge_graph_fingerprint: str,
    knowledge_graph_readiness_report: Dict[str, Any], knowledge_graph_build_summary: Dict[str, Any],
    final_graph_status: str,
    system_integrity_report: Dict[str, Any], determinism_report: Dict[str, Any],
    release_readiness_report: Dict[str, Any], release_status: str,
    build_metadata: Dict[str, Any], dependency_graph: Dict[str, Any],
    document_structure_tree=None,
    copyright_debug_entries: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Phase 1 Output Persistence Enhancement: persists every
    chapter-scoped Phase 1 artifact that, before this function existed,
    lived only in its own package's state.py module-level slots (see
    PHASE1_ARCHITECTURE.md). Every argument here is an already-computed
    value pipeline.process_chapter() collected above -- this function
    does not compute, validate, or reshape a single one of them, it
    only writes each to the storage location its own package's
    persistence.py module already defines.

    `document_structure_tree` (Milestone 5.2, optional -- defaults to
    None): the already-fully-assembled DST artifact Milestone 5.1's own
    pipeline-integration block built earlier in process_chapter()
    (`document_structure_tree.artifact.generate_artifact()`'s return
    value); never recomputed or revalidated here. Optional only so this
    function's own signature stays call-compatible with any hand-built
    caller that predates Milestone 5.2 -- process_chapter()'s own call
    site (below) always passes it.

    NEVER RAISES: mirrors runtime.runtime.CompilerRuntime._record_*()'s
    own "never raises" contract for exactly the same reason -- a
    persistence failure for one of these diagnostic/inspection
    artifacts must never mask or replace this chapter's real
    extraction outcome (the Chapter JSON write immediately before this
    call already succeeded by the time this runs). Each artifact type
    is wrapped in its own independent try/except so one artifact type
    failing to persist (e.g. a transient storage error) never prevents
    the others from being persisted.
    """
    storage = json_writer.get_storage()

    try:
        persist_registries(storage, registry_manager, klass, subject, book_slug, chapter_number,
                            chapter_title, output_root=output_root)
        persist_compiler_metadata(
            storage, klass, subject, book_slug, chapter_number, chapter_title,
            manifest=compiler_manifest, statistics=compiler_statistics,
            registry_fingerprints=compiler_registry_fingerprints,
            compiler_fingerprint=compiler_fingerprint,
            validation_report=compiler_validation_report,
            readiness_report=compiler_readiness_report,
            build_summary=compiler_build_summary,
            final_status=final_compiler_status,
            output_root=output_root,
        )
    except Exception:
        logger.warning("chapter '%s': failed to persist Compiler IR artifacts (registries/"
                        "compiler_metadata) -- chapter extraction outcome is unaffected.",
                        chapter_title, exc_info=True)

    try:
        persist_knowledge_graph(
            storage, klass, subject, book_slug, chapter_number, chapter_title,
            metadata=knowledge_graph_metadata,
            registry_manager=knowledge_graph_registry_manager,
            manifest=knowledge_graph_manifest, statistics=knowledge_graph_statistics,
            validation_report=knowledge_graph_validation_report,
            registry_fingerprints=knowledge_graph_registry_fingerprints,
            graph_fingerprint=knowledge_graph_fingerprint,
            readiness_report=knowledge_graph_readiness_report,
            build_summary=knowledge_graph_build_summary,
            final_status=final_graph_status,
            output_root=output_root,
        )
    except Exception:
        logger.warning("chapter '%s': failed to persist the Knowledge Graph -- chapter "
                        "extraction outcome is unaffected.", chapter_title, exc_info=True)

    if document_structure_tree is not None:
        try:
            persist_document_structure_tree(
                storage, klass, subject, book_slug, chapter_number, chapter_title,
                document_structure_tree=document_structure_tree,
                output_root=output_root,
            )
        except Exception:
            logger.warning("chapter '%s': failed to persist the Document Structure Tree -- "
                            "chapter extraction outcome is unaffected.", chapter_title, exc_info=True)

    try:
        persist_dependency_graph(storage, dependency_graph, klass, subject, book_slug, chapter_number,
                                  chapter_title, output_root=output_root)
    except Exception:
        logger.warning("chapter '%s': failed to persist the Dependency Graph -- chapter "
                        "extraction outcome is unaffected.", chapter_title, exc_info=True)

    try:
        persist_validation_record(
            storage, klass, subject, book_slug, chapter_number, chapter_title,
            system_integrity_report=system_integrity_report,
            determinism_report=determinism_report,
            release_readiness_report=release_readiness_report,
            release_status=release_status,
            output_root=output_root,
        )
    except Exception:
        logger.warning("chapter '%s': failed to persist the Stage D validation record -- "
                        "chapter extraction outcome is unaffected.", chapter_title, exc_info=True)

    try:
        _persist_build_metadata_record(storage, build_metadata, klass, subject, book_slug, chapter_number,
                                        chapter_title, output_root=output_root)
    except Exception:
        logger.warning("chapter '%s': failed to persist Build Metadata -- chapter extraction "
                        "outcome is unaffected.", chapter_title, exc_info=True)

    try:
        persist_extraction_debug(
            storage, klass, subject, book_slug, chapter_number, chapter_title,
            debug_entries=copyright_debug_entries or [],
            output_root=output_root,
        )
    except Exception:
        logger.warning("chapter '%s': failed to persist the Milestone 3.2 extraction-debug "
                        "record -- chapter extraction outcome is unaffected.",
                        chapter_title, exc_info=True)


def process_chapter(pdf_path: str, book_ctx: pdf_parser.BookContext, chapter_order_fallback: int,
                     use_vlm: bool = True, page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE,
                     force: bool = False, output_root: Optional[str] = None,
                     book_index: Optional[int] = None, total_books: Optional[int] = None,
                     processing_position: Optional[int] = None,
                     total_chapters_in_book: Optional[int] = None) -> Optional[str]:
    t0 = time.time()
    extraction_logs: Dict[str, Any] = {"warnings": [], "errors": [], "missing_figures": [],
                                        "ocr_failures": [], "parser_messages": []}

    structure = pdf_parser.parse_chapter_pdf(pdf_path, book_ctx, chapter_order_fallback)
    structure.book_title = book_ctx.book_title  # official title, attached for json_writer
    # Phase 1 Final Metadata Architecture Refinement: canonical distinguishing
    # cover metadata + the two derived identities, attached the same way
    # book_title always has been -- additive, optional fields json_writer
    # reads via getattr() so callers that build a bare ChapterStructure
    # double (pre-refinement tests) are unaffected.
    structure.book_subtitle = book_ctx.cover_subtitle
    structure.book_part = book_ctx.part
    structure.book_volume = book_ctx.volume
    structure.book_edition = book_ctx.edition
    structure.educational_identity = book_ctx.educational_identity
    structure.storage_identity = book_ctx.derived_storage_identity
    book_slug = slugify(pdf_parser.book_slug_source(book_ctx))  # output-directory identity, NOT necessarily the official title
    # A3 FIX (identity consistency): canonical_namespace / chapter_reference
    # are deliberately NOT computed here anymore. They must be derived from
    # the FINAL chapter title -- i.e. only after script-mismatch recovery
    # below has had a chance to correct structure.chapter_title -- because
    # every make_id()/make_urn() call further down in this function always
    # reads structure.chapter_title live (post-recovery). Freezing
    # canonical_namespace/chapter_reference off the pre-recovery title here
    # (as before) meant ids/urns could end up in a namespace/
    # chapter_reference that didn't match the title they were actually keyed
    # from whenever recovery changed the title. See the single computation
    # site below, right after script-mismatch recovery runs.

    # Every VLM prompt for this chapter should preserve structure.language
    # instead of assuming English (see modules/semantic_processor.py).
    semantic_processor.set_current_language(structure.language)
    # ISSUE 1 fix: clear the equation-semantics cache from any previous
    # chapter before this chapter's Stage A-E/VLM work starts (see
    # modules/semantic_processor.py's reset_chapter_state() docstring for
    # why this must never leak across chapters).
    semantic_processor.reset_chapter_state()
    # Phase B1 refinement (compiler/state.py): clear the *previous*
    # chapter's populated RegistryManager, if any, from the compiler's
    # current-compilation-state slot before this chapter's own registries
    # are built below -- same reasoning as reset_chapter_state() just
    # above, applied to the registry layer: a chapter that returns early
    # (already-extracted skip, or an exception) must never leave a stale
    # prior chapter's registries looking like "the current one" to any
    # later phase that reads compiler.get_current_registry_manager().
    compiler_state.reset_registry_state()

    if not force and json_writer.is_already_extracted(
            structure.klass, structure.subject, book_slug, structure.chapter_number, structure.chapter_title,
            output_root=output_root):
        logger.info("Skipping '%s' — chapter JSON already exists (resumable extraction). Use --force to redo.",
                     structure.chapter_title)
        return None

    _log_fields = [
        ("Book Progress", f"Book {book_index if book_index is not None else '?'} / "
                           f"{total_books if total_books is not None else '?'}"),
        ("Subject", book_ctx.subject),
        ("Book", book_ctx.educational_identity),
        ("Official Cover Title", book_ctx.book_title),
    ]
    # Only the distinguishing cover metadata NCERT actually printed for
    # THIS book ever shows up here -- the common single-part book (no
    # subtitle/Part/Volume) logs no such line at all, per STEP 5's
    # "don't display an empty subtitle line" requirement.
    if book_ctx.cover_subtitle:
        _log_fields.append(("Official Cover Subtitle", book_ctx.cover_subtitle))
    if book_ctx.part:
        _log_fields.append(("Part", book_ctx.part))
    if book_ctx.volume:
        _log_fields.append(("Volume", book_ctx.volume))
    _log_fields.extend([
        ("Storage Identity", book_ctx.derived_storage_identity),
        ("Current Processing Position", f"{processing_position}/{total_chapters_in_book}"
                                         if processing_position is not None else "?"),
        ("Actual Chapter Number", structure.chapter_number),
        ("Official Chapter Title", structure.chapter_title),
        ("Source PDF", os.path.basename(pdf_path)),
        ("Page Count", structure.num_pages),
        ("Detected Heading Count", len(structure.topics)),
    ])
    logger.info(
        "\n--------------------------------------------------\n%s\n"
        "--------------------------------------------------",
        "\n".join(f"{label}: {value}" for label, value in _log_fields),
    )

    # ---- OCR (per page, text-layer first, tesseract fallback) ----
    ocr_results = ocr_engine.ocr_chapter_pages(pdf_path, lang=structure.language)
    ocr_conf = ocr_engine.overall_ocr_confidence(ocr_results)
    ocr_text_by_page: Dict[int, str] = {r.page: r.text for r in ocr_results}
    for r in ocr_results:
        if r.engine == "none":
            extraction_logs["ocr_failures"].append(f"page {r.page}: no OCR engine available")
        elif r.engine == "text_layer_unverified":
            extraction_logs["warnings"].append(
                f"page {r.page}: text layer did not look like '{structure.language}' script (or OCR was "
                f"unavailable) — kept the raw text layer as a best-effort fallback; expect lower quality")
        elif r.engine.startswith("tesseract_fallback_"):
            extraction_logs["warnings"].append(
                f"page {r.page}: OCR language pack for '{structure.language}' unavailable — "
                f"fell back to '{r.engine.rsplit('_', 1)[-1]}' OCR")

    # ---- script-mismatch recovery (legacy-font Hindi/Sanskrit symptom) ----
    # Must run before Stage A below, since Stage A's block IDs are derived
    # from structure.chapter_title and should use the corrected title if one
    # was recovered. Requires the VLM, so it's skipped in --no-vlm dry runs
    # (same as every other AI-inferred field in this pipeline).
    if use_vlm:
        _doc_for_recovery = fitz.open(pdf_path)
        try:
            _recover_script_mismatched_text(_doc_for_recovery, structure, ocr_text_by_page, extraction_logs)
        finally:
            _doc_for_recovery.close()

    # A3 FIX (identity consistency): compute the shared urn namespace /
    # chapter_reference for every canonical object built in this chapter
    # HERE -- only now that structure.chapter_title is final (script-mismatch
    # recovery above is the last thing that can still change it) -- rather
    # than before recovery ran. Every make_id()/make_urn() call from this
    # point on in this function reads structure.chapter_title live, so this
    # is now guaranteed to be the exact same title every id/urn/
    # chapter_reference for this chapter is derived from. Deterministic:
    # slugify()/make_id()/make_urn() are pure functions of their string
    # inputs, so this introduces no randomness.
    chapter_slug = slugify(structure.chapter_title)
    canonical_namespace = f"{book_slug}:{chapter_slug}"
    chapter_reference = canonical_namespace

    # ---- deterministic layout detection (unchanged: purely geometric --
    # WHERE the visual/equation-line primitives are) ----
    layout = layout_detector.run_layout_detection(pdf_path)

    # ---- deterministic content-block detection (activities/boxes/notes/
    # warnings/examples) -- restored (see REGRESSION_AUDIT.md §3.3): still
    # used for the flat Master JSON sections below, in parallel with Stage
    # A/B's geometric grouping further down. ----
    topic_lookup = _topic_lookup_factory(structure)
    activities_raw = content_blocks.detect_activities(structure.lines, structure.repeated, structure.chapter_title)
    boxes_raw = content_blocks.detect_boxes(structure.lines, structure.repeated, structure.chapter_title)
    warnings_raw = content_blocks.detect_warnings(structure.lines, structure.repeated, structure.chapter_title)
    notes_raw = content_blocks.detect_notes(structure.lines, structure.repeated, structure.chapter_title)
    examples_raw = content_blocks.detect_examples(structure.lines, structure.repeated, structure.chapter_title)
    definitions = content_blocks.detect_definition_terms(structure.lines, structure.repeated, topic_lookup)
    for idx, d in enumerate(definitions):
        d.pop("_body_for_semantic", None)
        # A1/A3: Definition previously had no id/urn at all -- content_blocks
        # only ever emitted {term, page, topic, bbox}. Deterministic id/urn
        # generated here (term + page, the only stable content key
        # available at this deterministic-only stage) rather than inside
        # content_blocks.py, so Stage-labeled deterministic-extraction logic
        # (content_blocks.detect_definition_terms itself) stays untouched
        # per the roadmap's "do not redesign existing deterministic
        # extraction logic".
        d.update(canonical.canonical_fields(
            object_id=make_id(structure.chapter_title, "definition", d["term"], str(d.get("page")), str(idx)),
            object_type="definition", namespace=canonical_namespace,
            # STEP 4 AUDIT FIX (same bug class as glossary): object_id
            # above includes `idx` so it is always unique, but urn_parts
            # previously omitted it -- two definition-term occurrences for
            # the exact same term text on the exact same page (both
            # legitimate, distinct DefinitionRegistry records per
            # test_same_term_different_pages_both_insert_without_conflict)
            # would get different ids but the identical urn, i.e. the same
            # latent DuplicateUrnError this task's Phase 1 fixed for
            # glossary. `idx` added so id/urn always agree.
            urn_parts=["definition", d["term"], str(d.get("page")), str(idx)],
            subject=structure.subject, chapter_reference=chapter_reference,
            topic_ids=[d["topic"]] if d.get("topic") else [],
            source_page=d.get("page"), bounding_box=d.get("bbox"),
            extraction_stage="content_blocks.detect_definition_terms",
            extraction_method="deterministic", confidence=0.6,
        ))

    doc = fitz.open(pdf_path)

    # ---- topics: deterministic fields + VLM semantic fields -- restored ----
    topics_out: List[Dict[str, Any]] = []
    # Canonical Concept Registry (Single Owner Principle): concepts are
    # deduped by case-insensitive name across the WHOLE chapter, not
    # per-topic-occurrence. Before this fix, the same concept name
    # mentioned in two different topics produced two separate `all_concepts`
    # records that collided on `id` (make_id() hashes chapter+name, not
    # topic) but disagreed on `topic` -- a broken canonical registry where
    # "same id, two records" made every id-keyed lookup downstream
    # (graph_builder.build_concept_graph's name_to_id map, semantic_index)
    # silently pick whichever record happened to be built last. Now each
    # distinct concept name gets exactly one canonical record with a
    # stable id + urn and a `topics` list of every topic that mentions it.
    #
    # DUPLICATE-ID INVESTIGATION FIX (populate_registries() DuplicateIdError
    # on e.g. "...-concept-science-vs-art-<hash>"): the dedup key here used
    # to be plain `name.lower()` -- case-insensitive only. The canonical id
    # itself, though, is `make_id(chapter_title, "concept", name)`, which is
    # built via slugify(), and slugify() folds far more than case: EVERY
    # non-letter/mark/number character (spaces, periods, extra whitespace,
    # ...) collapses to a single '-'. So two VLM-returned name spellings
    # that differ only in punctuation/whitespace -- e.g. "Science vs Art"
    # and "Science vs. Art" (a realistic same-concept, different-topic VLM
    # phrasing difference) -- hashed to DIFFERENT `name.lower()` keys (so
    # this dict happily created two separate concept_registry records) but
    # the IDENTICAL make_id()/make_urn() id/urn (so those two records
    # disagree with the dedup key about what makes two mentions "the same
    # concept"). Nothing ever surfaced this before Phase B1's
    # populate_registries() -> CanonicalRegistry.insert() started enforcing
    # real id-uniqueness on every concept object: the old pipeline just
    # silently shipped two same-id concept records in the Chapter JSON's
    # flat `concepts` list. The dedup key must therefore be derived the
    # SAME way the id itself is (slugify()), not a weaker, independent
    # normalization -- otherwise "two records, same id" is always possible
    # for punctuation/whitespace-only spelling differences, regardless of
    # what registry-layer validation exists downstream.
    concept_registry: Dict[str, Dict[str, Any]] = {}
    glossary: List[Dict[str, Any]] = []
    for t in structure.topics:
        sem = semantic_processor.process_topic_semantics(doc, t) if use_vlm else {}
        concepts_list = sem.get("concepts", []) or []
        this_topic_concept_names: List[str] = []
        for cname in concepts_list:
            name = str(cname).strip()
            if not name:
                continue
            this_topic_concept_names.append(name)
            # Same normalization make_id()/make_urn() use for this exact
            # (chapter_title, "concept", name) triple, so two name spellings
            # that would collide on canonical id always collide on this key
            # too -- see the DUPLICATE-ID INVESTIGATION FIX comment above.
            key = slugify(name)
            existing = concept_registry.get(key)
            if existing is None:
                # A1/A2/A3: id/urn generated the same way as before (same
                # inputs, same make_id/make_urn -- see modules/pdf_parser.py
                # -- so pre-Phase-A urns for existing concepts are
                # byte-for-byte unchanged); everything else here is the new
                # canonical envelope (A1) merged in via canonical_fields().
                concept_registry[key] = {
                    **canonical.canonical_fields(
                        object_id=make_id(structure.chapter_title, "concept", name),
                        object_type="concept", namespace=canonical_namespace,
                        urn_parts=["concept", name],
                        subject=structure.subject, chapter_reference=chapter_reference,
                        topic_ids=[t.id], source_page=t.page_start, source_heading=t.title,
                        extraction_stage="semantic_processor.process_topic_semantics",
                        extraction_method="vlm" if use_vlm else "deterministic", confidence=0.5,
                    ),
                    "name": name, "aliases": [], "importance": "medium",
                    "topic": t.id, "topics": [t.id], "page": t.page_start,
                    "related_concepts": [],
                }
            elif t.id not in existing["topics"]:
                existing["topics"].append(t.id)
        # ROOT CAUSE: `object_id` below is (and always was) generated from
        # (chapter_title, "glossary", term_s, t.id) -- unique per (term,
        # topic) occurrence, matching GlossaryRegistry's own documented
        # contract ("one record per (term, topic) glossary occurrence",
        # compiler/registries.py) and the frozen
        # test_same_term_different_topics_both_insert unit test, which
        # both expect two DIFFERENT topics mentioning the same term to
        # produce two DIFFERENT, both-valid glossary records. But the urn
        # was built from `urn_parts=["glossary", term_s]` -- term only,
        # never `t.id` -- so it did NOT carry the same distinguishing
        # information as the id. Two legitimate (term, topic) occurrences
        # for the same term therefore got two different ids but the exact
        # same urn, which is precisely "duplicate urn ... already resolves
        # to a different id" from the runtime log: the registry correctly
        # rejected an object whose own id/urn generation disagreed with
        # itself about what makes it unique.
        #
        # Fix: urn_parts now includes `t.id`, exactly like object_id
        # already does, so id and urn are always derived from the same
        # inputs -- one glossary urn per (term, topic) pair, never per
        # term alone. This is the minimum change that makes id and urn
        # agree; it does not alter what GlossaryRegistry accepts.
        #
        # Separately, a VLM call can return the same term string more than
        # once for one topic (e.g. the term appears in more than one
        # educational block within that topic) -- that IS a true, same-
        # topic duplicate, not two legitimate occurrences, so it is
        # deduplicated here using the compiler's own canonical identity
        # primitive, `canonical_lookup_key()` (compiler/normalization.py:
        # NFKC normalize, quote/dash fold, invisible-char strip, whitespace
        # collapse, casefold, edge-punctuation strip) -- reused rather than
        # reimplemented, so "same term" here always means what the rest of
        # the compiler already means by it.
        seen_glossary_keys_this_topic: set = set()
        for term in sem.get("glossary_terms", []) or []:
            term_s = str(term).strip()
            if not term_s:
                continue
            term_key = canonical_lookup_key(term_s) or term_s.casefold()
            if term_key in seen_glossary_keys_this_topic:
                continue
            seen_glossary_keys_this_topic.add(term_key)
            glossary.append({
                **canonical.canonical_fields(
                    object_id=make_id(structure.chapter_title, "glossary", term_s, t.id),
                    object_type="glossary_entry", namespace=canonical_namespace,
                    urn_parts=["glossary", term_s, t.id],
                    subject=structure.subject, chapter_reference=chapter_reference,
                    topic_ids=[t.id], source_page=t.page_start, source_heading=t.title,
                    extraction_stage="semantic_processor.process_topic_semantics",
                    extraction_method="vlm" if use_vlm else "deterministic", confidence=0.5,
                ),
                "term": term_s, "topic": t.id, "page": t.page_start,
            })

        # A4: canonical concept references. `this_topic_concept_names` are
        # display names (kept as derived metadata); `this_topic_concept_ids`
        # -- resolvable in-loop since concept_registry already has an entry
        # for every name in this_topic_concept_names by this point -- is the
        # canonical reference stored in TopicNode.concepts.
        this_topic_concept_ids = [
            concept_registry[slugify(n)]["id"] for n in this_topic_concept_names if slugify(n) in concept_registry
        ]

        topics_out.append({
            "id": t.id, "title": t.title, "numbering": t.numbering, "level": t.level,
            "parent": t.parent, "children": [], "page_start": t.page_start, "page_end": t.page_end,
            "bbox": {"x0": t.bbox[0], "y0": t.bbox[1], "x1": t.bbox[2], "y1": t.bbox[3], "page": t.page_start},
            "reading_order": t.reading_order, "keywords": [],
            "concepts": this_topic_concept_ids,
            "concept_names": this_topic_concept_names,
            "definitions": [d["term"] for d in definitions if d.get("topic") == t.id],
            "examples": [], "activities": [], "figures": [], "tables": [], "equations": [],
            "diagrams": [], "charts": [], "graphs": [], "maps": [], "timelines": [],
            "boxes": [], "notes": [], "warnings": [],
            "semantic_summary": sem.get("semantic_summary", ""),
            "visual_summary": sem.get("visual_summary", ""),
            "detected_entities": sem.get("detected_entities", []) or [],
            "prerequisites": sem.get("prerequisites", []) or [],
            "related_topics": sem.get("related_topics", []) or [],
            "next_topics": [],
            "confidence": sem.get("confidence", t.confidence),
        })
    # Materialize the canonical registry into the flat list every existing
    # consumer (graph_builder, json_writer, Concept schema) expects. One
    # canonical record per distinct concept name, not one per mention.
    all_concepts: List[Dict[str, Any]] = list(concept_registry.values())
    # fill children[] now that all ids exist
    id_to_index = {tp["id"]: i for i, tp in enumerate(topics_out)}
    for tp in topics_out:
        if tp["parent"] and tp["parent"] in id_to_index:
            topics_out[id_to_index[tp["parent"]]]["children"].append(tp["id"])
    for i, tp in enumerate(topics_out):
        tp["next_topics"] = [topics_out[i + 1]["title"]] if i + 1 < len(topics_out) else []

    # A4: chapter-wide concept name -> concept id lookup, built once the
    # registry is final, for every remaining object type below that may
    # reference concepts by name (figures/tables/diagrams/activities/...).
    concept_name_to_id: Dict[str, str] = {name: rec["id"] for name, rec in concept_registry.items()}

    def _attach_canonical(obj: Dict[str, Any], *, object_type: str, urn_parts: List[str],
                           concept_names: Optional[List[str]] = None, topic_ids: Optional[List[str]] = None,
                           source_page: Optional[int] = None, source_block_id: Optional[str] = None,
                           source_heading: Optional[str] = None, extraction_stage: Optional[str] = None,
                           extraction_method: str = "deterministic",
                           confidence: Optional[float] = None) -> Dict[str, Any]:
        """A1/A2/A4 assembly-time helper (closes over this chapter's
        book_slug/chapter_slug/structure/chapter_reference/
        concept_name_to_id): attaches the common canonical envelope to an
        already-built object dict (`obj` must already have "id" -- this
        never mints a new one, see canonical.canonical_fields) and resolves
        `concept_names` to canonical concept_ids. Used below for every
        object type not already handled inline (concepts/topics/glossary
        above build their own envelope directly since concept_ids aren't
        yet resolvable from a shared map at that point in the loop)."""
        cids = canonical.resolve_concept_ids(concept_names or [], concept_name_to_id)
        obj.update(canonical.canonical_fields(
            object_id=obj["id"], object_type=object_type, namespace=canonical_namespace,
            urn_parts=urn_parts, subject=structure.subject, chapter_reference=chapter_reference,
            topic_ids=topic_ids or [], concept_ids=cids,
            source_page=source_page if source_page is not None else obj.get("page"),
            source_block_id=source_block_id, source_heading=source_heading,
            bounding_box=obj.get("bbox"), extraction_stage=extraction_stage,
            extraction_method=extraction_method,
            confidence=confidence if confidence is not None else obj.get("confidence", 0.5),
        ))
        if cids:
            obj["concept_ids"] = cids
        return obj

    # ---- figures / tables / equations / diagrams / charts / graphs / maps
    # / timelines -- restored. Figures/tables/diagrams stay deterministic
    # -only (matches original behavior, and Stage D's VisualFamilyRecognizer
    # below, gated by config.ENABLE_VISUAL_VLM); equations still go through
    # the VLM for every detected region, same as before Stage D existed. ----
    figures, tables, equations = [], [], []
    diagrams, charts, graphs_, maps_, timelines = [], [], [], [], []

    # A4 review (Fix 3, Phase A finalization): Figure/Table/Diagram.concept_ids
    # are intentionally left as [] below (via _attach_canonical's default
    # concept_names=None -> resolve_concept_ids([], ...) -> []), same as
    # before this review. Reviewed whether any existing deterministic
    # pipeline output could populate them: layout_detector's figure/table/
    # diagram regions only carry page/bbox/title/caption -- there is no
    # deterministic (non-guessed) link from a region to specific concept
    # NAMES the way content_blocks.detect_definition_terms or
    # semantic_processor.process_topic_semantics's glossary/concepts output
    # give definitions/glossary entries a name to resolve against
    # concept_name_to_id. The only way to populate concept_ids today would be
    # to guess from region.caption/region.title text (string/substring
    # matching against concept_registry names) or the enclosing topic's
    # concept list by page-range containment -- both are heuristics, not
    # existing deterministic information, and the roadmap explicitly rules
    # out inventing concept links or heuristic guessing here. Richer visual
    # concept linking (e.g. VLM-identified concepts depicted in a figure/
    # table/diagram) is therefore intentionally deferred to Phase B.
    for idx, region in enumerate(layout["figures"]):
        figures.append({
            "id": _region_to_id("figure", structure.chapter_title, region, idx), "page": region.page,
            "bbox": {"x0": region.bbox[0], "y0": region.bbox[1], "x1": region.bbox[2], "y1": region.bbox[3],
                     "page": region.page},
            "title": region.title, "caption": region.caption,
            "figure_type": "figure",
            "semantic_description": "", "educational_purpose": "",
            "concepts": [], "related_topics": [],
            "importance": "medium", "difficulty": "medium",
            "animation_candidate": False, "confidence": 0.5,
        })
        _attach_canonical(figures[-1], object_type="figure",
                           urn_parts=["figure", str(region.page), str(idx)],
                           source_page=region.page,
                           extraction_stage="layout_detector.detect_figures", confidence=0.5)

    for idx, region in enumerate(layout["diagrams"]):
        diagrams.append({
            "id": _region_to_id("diagram", structure.chapter_title, region, idx), "page": region.page,
            "bbox": {"x0": region.bbox[0], "y0": region.bbox[1], "x1": region.bbox[2], "y1": region.bbox[3],
                     "page": region.page},
            "title": region.title, "caption": region.caption,
            "figure_type": "diagram", "semantic_description": "", "educational_purpose": "",
            "concepts": [], "related_topics": [],
            "importance": "medium", "difficulty": "medium",
            "animation_candidate": False, "confidence": 0.5,
        })
        _attach_canonical(diagrams[-1], object_type="diagram",
                           urn_parts=["diagram", str(region.page), str(idx)],
                           source_page=region.page,
                           extraction_stage="layout_detector.detect_diagrams", confidence=0.5)

    for idx, region in enumerate(layout["tables"]):
        extra = region.extra or {}
        tables.append({
            "id": _region_to_id("table", structure.chapter_title, region, idx), "title": region.caption,
            "page": region.page,
            "bbox": {"x0": region.bbox[0], "y0": region.bbox[1], "x1": region.bbox[2], "y1": region.bbox[3],
                     "page": region.page},
            "rows": extra.get("rows", 0), "columns": extra.get("columns", 0),
            "table_type": "data_table",
            "semantic_description": "", "educational_purpose": "", "concepts": [],
            "confidence": 0.5,
        })
        _attach_canonical(tables[-1], object_type="table",
                           urn_parts=["table", str(region.page), str(idx)],
                           source_page=region.page,
                           extraction_stage="layout_detector.detect_tables", confidence=0.5)

    # ---- Stage A: Geometry Segmentation ------------------------------------
    # WHERE are the blocks? Consumes structure.lines (text layer) + layout's
    # visual regions (visual layer). Groups e.g. Formula/Calculation/
    # Calculation/Answer equation lines into ONE hierarchical block instead
    # of 4 independent VisualRegions. No classification, no VLM. Kept
    # unchanged (this is the genuinely useful optimization) -- its output
    # (`blocks`) is now folded into the same Master JSON as everything
    # above, instead of replacing it (see REGRESSION_AUDIT.md).
    #
    # ISSUE 1/3/4 fix: this now runs BEFORE the flat `equations` list is
    # built below (it used to run after), specifically so the flat list can
    # consult Stage B's classification -- see the region-lookup and
    # equation_intent gating right below -- instead of unconditionally
    # calling the equation_analysis VLM task for every single detected
    # equation region regardless of whether Stage B already knows it's a
    # Worked-Example/Exercise substitution step rather than reusable
    # knowledge. This is what removes the duplicate/redundant VLM cost the
    # audit found (equation_analysis running once here unconditionally,
    # and again inside Stage D's FormulaFamilyRecognizer for the same
    # region once it had been classified) instead of merely caching around
    # it (see modules/semantic_processor.py's equation-semantics cache for
    # the belt-and-suspenders backstop covering any block Stage D itself
    # widens/merges beyond a single region).
    blocks = stage_a_geometry.build_hierarchical_blocks(structure, layout)

    # ---- Stage B: Educational Block Classification -------------------------
    # WHAT is the block? Pure deterministic classification behind
    # classify(block); no VLM. Ambiguous blocks stay Ambiguous.
    blocks = stage_b_classify.classify_blocks(blocks)

    # ---- Stage C: Educational Priority Assignment ---------------------------
    # HOW IMPORTANT is the block? Nothing is discarded at this stage -- every
    # block (including Low priority ones) stays in `blocks` for lineage.
    blocks = stage_c_priority.assign_priority(blocks)

    # Region -> (block_type, raw_text) lookup, built from Stage A/B's
    # equation-cluster blocks. Stage A's _cluster_equation_regions wraps
    # every layout["equations"] region as one "equation-line" child block
    # (child.page/child.bbox == region.page/region.bbox exactly, since it's
    # built directly from that same region -- see stage_a_geometry.py), and
    # Stage B classifies the *parent* equation-cluster block (Formula Box /
    # Worked Example / ...), not the individual child lines. Mapping each
    # child's (page, bbox) back to its parent's block_type/confidence/raw
    # text is therefore exact -- no re-derivation or fuzzy bbox matching
    # needed -- and requires no change to Stage A's return signature.
    _equation_region_info: Dict[Tuple[int, Tuple[float, float, float, float]], Dict[str, Any]] = {}
    for b in blocks:
        if (b.grouping_meta or {}).get("anchor") != "equation-cluster":
            continue
        cluster_raw_text = " ".join(
            (c.grouping_meta or {}).get("raw_text", "") for c in b.children) or " ".join(
            l.text for l in b.lines)
        for child in b.children:
            key = (child.page, tuple(round(float(v), 1) for v in child.bbox))
            _equation_region_info[key] = {
                "block_type": b.block_type, "confidence": b.confidence,
                "priority": b.priority, "raw_text": cluster_raw_text,
            }

    for idx, region in enumerate(layout["equations"]):
        key = (region.page, tuple(round(float(v), 1) for v in region.bbox))
        info = _equation_region_info.get(key, {})
        raw_text_hint = info.get("raw_text") or (region.extra or {}).get("raw_text", "")
        run_vlm = use_vlm and equation_intent.introduces_reusable_knowledge(
            info.get("block_type"), raw_text_hint)

        if run_vlm:
            sem = semantic_processor.process_equation_semantics(doc, region)
        else:
            sem = {}

        eq_record = {
            "id": _region_to_id("equation", structure.chapter_title, region, idx), "page": region.page,
            "bbox": {"x0": region.bbox[0], "y0": region.bbox[1], "x1": region.bbox[2], "y1": region.bbox[3],
                     "page": region.page},
            "latex": sem.get("latex", ""), "spoken_form": sem.get("spoken_form", ""),
            "variables": sem.get("variables", []) or [],
            "semantic_meaning": sem.get("semantic_meaning", ""),
            "confidence": float(sem.get("confidence", 0.5) or 0.5),
            # ISSUE 5 fix: preserved regardless of whether equation_analysis
            # ran, so nothing about WHERE/WHAT the equation is disappears
            # from the Master JSON just because its semantic analysis was
            # skipped as low-value.
            "raw_text": raw_text_hint,
            "block_type": info.get("block_type"),
            "educational_intent": "introduces_reusable_knowledge" if run_vlm
            else ("uses_existing_knowledge" if use_vlm else "unknown_vlm_disabled"),
            "vlm_analysis_skipped": (not run_vlm) and use_vlm,
        }
        if use_vlm and not run_vlm:
            eq_record["skip_reason"] = equation_intent.skip_reason(info.get("block_type"), raw_text_hint)
        if sem.get("_vlm_failed"):
            # ISSUE 2 fix: a VLM call that never produced valid JSON no
            # longer silently disappears -- the raw text is preserved here
            # instead so the pipeline can be reprocessed/audited later
            # rather than that equation's semantics being lost forever.
            eq_record["vlm_raw_output"] = sem.get("_vlm_raw_output", "")
            eq_record["vlm_validation_errors"] = sem.get("_vlm_validation_errors", [])
        equations.append(eq_record)
        _attach_canonical(eq_record, object_type="equation",
                           urn_parts=["equation", str(region.page), str(idx)],
                           source_page=region.page,
                           extraction_stage="stage_a_geometry+equation_intent",
                           extraction_method="vlm" if run_vlm else "deterministic",
                           confidence=eq_record["confidence"])

    # ---- content blocks -> final records -- restored ----
    # Milestone 3.3 fix: this used to set `semantic_description` directly
    # from `_enforce_word_cap(body[:200])` -- a raw character-slice of the
    # block's own source text. Capping the word count shortens copied
    # prose, it does not stop it being copied prose, so that was still a
    # source-text leak (M3.1 §2.1 MEDIUM finding, deferred by M3.2). The
    # raw excerpt is now handed to `copyright_sanitizer.sanitize_content_blocks`
    # below instead, which strips it into the debug artifact and leaves
    # `semantic_description` empty -- the same interim behavior Figures/
    # Tables/Equations already have at Phase 1, pending a real paraphrase
    # step. `_body_for_semantic` itself never reaches the sanitizer or the
    # production record; only its capped preview does, and only as debug
    # payload.
    def _finalize_blocks(raw_list):
        out = []
        for item in raw_list:
            body = item.pop("_body_for_semantic", "")
            item["semantic_description"] = semantic_processor._enforce_word_cap(body[:200])
            out.append(item)
        return out

    activities = _finalize_blocks(activities_raw)
    boxes = _finalize_blocks(boxes_raw)
    warnings_list = _finalize_blocks(warnings_raw)
    notes = _finalize_blocks(notes_raw)
    examples = _finalize_blocks(examples_raw)

    # STEP 4 AUDIT FIX (same bug class as glossary/definitions above): each
    # of these five dicts already carries an `id` built by
    # content_blocks.py from (chapter_title, type, ..., a per-line `idx`
    # unique across the whole chapter -- see e.g. detect_activities'
    # `make_id(chapter_title, "activity", label, str(idx))`), but the urn
    # built below only used (type, sub-type, page) -- with no positional
    # disambiguator. Two Activity blocks of the same activity_type on the
    # same page (equally, two Box/Warning/Note/Example blocks sharing
    # type+page) would get different, correctly-unique ids but collide on
    # urn -- the identical "different id, same urn" DuplicateUrnError this
    # task fixed for glossary. Fix: enumerate() each list (list order is
    # preserved 1:1 from content_blocks.py's own idx-ordered output -- see
    # _finalize_blocks above, which only pops a key and sets one field,
    # never reorders or filters) and fold that position into urn_parts, so
    # every urn gets the same positional disambiguator its id already has.
    for idx, a in enumerate(activities):
        _attach_canonical(a, object_type="activity",
                           urn_parts=["activity", a.get("activity_type", ""), str(a.get("page")), str(idx)],
                           extraction_stage="content_blocks.detect_activities", confidence=0.6)
    for idx, bx in enumerate(boxes):
        _attach_canonical(bx, object_type="box",
                           urn_parts=["box", bx.get("box_type", ""), str(bx.get("page")), str(idx)],
                           extraction_stage="content_blocks.detect_boxes", confidence=0.6)
    for idx, w in enumerate(warnings_list):
        _attach_canonical(w, object_type="warning",
                           urn_parts=["warning", w.get("warning_type", ""), str(w.get("page")), str(idx)],
                           extraction_stage="content_blocks.detect_warnings", confidence=0.6)
    for idx, n in enumerate(notes):
        _attach_canonical(n, object_type="note", urn_parts=["note", str(n.get("page")), str(idx)],
                           extraction_stage="content_blocks.detect_notes", confidence=0.6)
    for idx, ex in enumerate(examples):
        _attach_canonical(ex, object_type="example", urn_parts=["example", str(ex.get("page")), str(idx)],
                           extraction_stage="content_blocks.detect_examples", confidence=0.6)

    # ---- Milestone 1: Universal Object Linking ---------------------------
    # Concepts, glossary entries, and definitions were already linked to
    # their enclosing topic above (topic_ids set inline at construction
    # time -- see the topic-construction loop and
    # content_blocks.detect_definition_terms's topic_lookup argument).
    # Every other canonical object type built above (figures/diagrams/
    # tables/equations/activities/boxes/warnings/notes/examples) went
    # through _attach_canonical() with no topic_ids= argument, so it
    # defaulted to [] -- see modules/topic_linker.py's module docstring
    # (BACKGROUND section) for the full explanation. This single,
    # reusable, object-type-agnostic pass closes that gap: it resolves
    # each of those nine types' topic_ids via deterministic page-range
    # containment (never a caption/title guess) and populates the
    # matching reverse-reference list (examples/figures/tables/.../
    # warnings) on each `topics_out` entry in place. Must run after every
    # object list above is fully built (every object's `page` is already
    # set) and after topics_out's own page_start/page_end/id are final
    # (set above, before `concept_name_to_id` is built) -- exactly where
    # this call sits.
    topic_linking_stats = topic_linker.link_universal_objects(
        topics=topics_out,
        examples=examples, tables=tables, figures=figures, diagrams=diagrams,
        equations=equations, notes=notes, boxes=boxes, activities=activities,
        warnings=warnings_list,
    )

    # ---- graphs + semantic index -- restored ----
    learning_graph = graph_builder.build_learning_graph(topics_out)
    concept_graph = graph_builder.build_concept_graph(all_concepts)
    semantic_index = graph_builder.build_semantic_index(all_concepts, topics_out, definitions,
                                                          figures + diagrams + charts + graphs_ + maps_ + timelines,
                                                          tables, equations)

    # ---- chapter-level AI metadata + generation metadata (VLM) -- restored ----
    if use_vlm:
        ai_metadata = semantic_processor.process_chapter_ai_metadata(
            [t["title"] for t in topics_out], len(figures), len(tables), len(equations))
        generation_metadata = semantic_processor.process_generation_metadata(structure.chapter_title, ai_metadata)
        # A4: ai_metadata's important_concepts / likely_confusing_concepts
        # are VLM-returned display names (no VLM prompt change needed/made
        # here -- see IMPLEMENTATION RULES #2, do not introduce unnecessary
        # VLM calls). The *_ids lists are the added canonical reference,
        # resolved deterministically against this chapter's concept
        # registry; names are left in place as the derived, human-readable
        # metadata per A4.
        ai_metadata["important_concept_ids"] = canonical.resolve_concept_ids(
            ai_metadata.get("important_concepts", []) or [], concept_name_to_id)
        ai_metadata["likely_confusing_concept_ids"] = canonical.resolve_concept_ids(
            ai_metadata.get("likely_confusing_concepts", []) or [], concept_name_to_id)
    else:
        ai_metadata, generation_metadata = {}, {}

    # ---- Stage D: Scoped Educational Extraction ------------------------------
    # Only High/Medium-priority blocks are processed; deterministic template
    # tried first, VLM called only when that template can't identify the
    # reusable formula/procedure with sufficient confidence. This is
    # additive to (not a replacement for) the topics/figures/tables/
    # equations built above.
    educational_objects = stage_d_extraction.extract_educational_objects(
        blocks, doc, use_vlm=use_vlm, chapter_title=structure.chapter_title)

    # ---- Stage E: Educational Validation --------------------------------------
    # Pure deterministic validation: removes duplicate formulas/definitions/
    # bare-arithmetic leftovers, preserves block_id/bbox/page/lineage.
    educational_objects, validation_report = stage_e_validation.validate_educational_objects(educational_objects)

    # ---- Knowledge-Graph readiness (PART 2 of this task) ----------------------
    # Does NOT build any graph (no nodes/edges/prerequisite or dependency
    # graphs -- that remains entirely Phase 2's job). Only attaches context
    # (parent chapter/heading/sub-heading, hierarchy path, reading/block
    # order, local text context, nearby objects, ...) and semantic metadata
    # (educational role, introduces/explains/applies/demonstrates/
    # references concept, cross references, visual/table support,
    # prerequisite/dependency candidates, ...) to each already-validated
    # educational object, so Phase 2 can build its graphs from this Master
    # JSON alone without re-reading the source PDF.
    educational_objects = kg_readiness.enrich_educational_objects(
        educational_objects, blocks, topics_out, structure.chapter_title,
        figures=figures, tables=tables, equations=equations,
    )

    # ---- Milestone 3.2: Copyright-Safe Serialization ---------------------
    # Implements the M3.1 audit's HIGH-risk findings (see
    # modules/copyright_sanitizer.py's own module docstring for the full
    # field list and reasoning). Deliberately runs HERE, after Stage E
    # (stage_e_validation.validate_educational_objects, above -- which
    # reads `reusable_procedure`'s own CONTENT, not just its presence, to
    # decide whether an object is bare-arithmetic/duplicate junk) and
    # after kg_readiness.enrich_educational_objects (which only reads
    # already-SAFE fields: block_id/bbox/page/educational_object_type/
    # confidence -- never the HIGH-risk prose fields this sanitizes), but
    # BEFORE `equations`/`educational_objects` are handed to
    # populate_registries() (Compiler IR) or json_writer.assemble_chapter_json()
    # (production Chapter JSON) below -- i.e. after every legitimate
    # deterministic consumer of the raw content has already run, and
    # before every downstream artifact that must never carry it.
    #
    # `equations`/`educational_objects` are reassigned to their sanitized
    # versions so every later reader in this function (registries,
    # quality scoring, chapter_dict assembly, DST) sees only the
    # copyright-safe shape -- there is no second, unsanitized copy left
    # anywhere in this function's scope.
    equations, educational_objects, _copyright_debug_entries = (
        copyright_sanitizer.sanitize_chapter_records(equations, educational_objects)
    )

    # ---- Milestone 3.3: Copyright-Safe Serialization, cont'd -------------
    # The MEDIUM/LOW findings M3.2 deferred (see copyright_sanitizer.py's
    # module docstring, "Milestone 3.3 additions"). Run at the same
    # checkpoint as the M3.2 call directly above, for the same reason: by
    # this point Stage E and KG-readiness have already read whatever they
    # needed from `figures`/`tables`/`diagrams`, and nothing downstream of
    # here (registries, chapter_dict assembly, DST) may see raw content-
    # block descriptions or uncapped captions. Every list here is mutated
    # in place via .append() from where it was first built, never
    # reassigned, so these are still the same objects that will be
    # written into the production Chapter JSON below -- reassigning each
    # to its sanitized version keeps that "no second unsanitized copy"
    # guarantee.
    activities_report = copyright_sanitizer.sanitize_content_blocks(activities, record_type="activity")
    boxes_report = copyright_sanitizer.sanitize_content_blocks(boxes, record_type="box")
    warnings_report = copyright_sanitizer.sanitize_content_blocks(warnings_list, record_type="warning")
    notes_report = copyright_sanitizer.sanitize_content_blocks(notes, record_type="note")
    examples_report = copyright_sanitizer.sanitize_content_blocks(examples, record_type="example")
    activities, boxes, warnings_list, notes, examples = (
        activities_report.sanitized, boxes_report.sanitized, warnings_report.sanitized,
        notes_report.sanitized, examples_report.sanitized,
    )

    figures_report = copyright_sanitizer.sanitize_visual_captions(figures, record_type="figure")
    diagrams_report = copyright_sanitizer.sanitize_visual_captions(diagrams, record_type="diagram")
    tables_report = copyright_sanitizer.sanitize_visual_captions(tables, record_type="table")
    figures, diagrams, tables = (
        figures_report.sanitized, diagrams_report.sanitized, tables_report.sanitized,
    )

    _copyright_debug_entries = (
        _copyright_debug_entries
        + activities_report.debug_entries + boxes_report.debug_entries
        + warnings_report.debug_entries + notes_report.debug_entries
        + examples_report.debug_entries
        + figures_report.debug_entries + diagrams_report.debug_entries
        + tables_report.debug_entries
    )

    quality = {
        "ocr": ocr_conf, "heading": round(sum(t.confidence for t in structure.topics) / max(1, len(structure.topics)), 3),
        "layout": 1.0 if (figures or tables or equations) else 0.8,
        "table": round(sum(t.get("confidence", 0.5) for t in tables) / max(1, len(tables)), 3) if tables else 0.0,
        "figure": round(sum(f.get("confidence", 0.5) for f in figures) / max(1, len(figures)), 3) if figures else 0.0,
        "equation": round(sum(e.get("confidence", 0.5) for e in equations) / max(1, len(equations)), 3) if equations else 0.0,
        "block_classification": round(
            sum(b.confidence for b in blocks) / max(1, len(blocks)), 3) if blocks else 0.0,
        "extraction": round(
            sum(o.get("confidence", 0.0) for o in educational_objects) / max(1, len(educational_objects)), 3
        ) if educational_objects else 0.0,
    }
    _quality_components = [v for k, v in quality.items() if k != "overall"]
    quality["overall"] = round(sum(_quality_components) / max(1, len(_quality_components)), 3)

    extraction_logs["processing_time"] = round(time.time() - t0, 2)
    extraction_logs["parser_messages"].append(
        f"{len(structure.topics)} heading(s) detected, TOC matched={structure.toc_matched}")
    extraction_logs["parser_messages"].append(
        f"Stage A-C: {len(blocks)} block(s) classified; Stage D-E: {len(educational_objects)} "
        f"validated educational object(s) ({validation_report['removed_duplicate_formulas']} duplicate "
        f"formula(s), {validation_report['removed_duplicate_definitions']} duplicate definition(s), "
        f"{validation_report['removed_bare_arithmetic']} bare-arithmetic object(s) removed).")

    # ---- Phase B1: canonical registry population -----------------------------
    # Symbol-table layer for this compiler run: every canonical educational
    # object this chapter built above (concepts/definitions/glossary/figures/
    # diagrams/tables/equations/activities/boxes/warnings/notes/examples) is
    # inserted into its matching CanonicalRegistry (compiler/registries.py),
    # owned by one RegistryManager for this chapter. Insertion order matches
    # each list's own order above -- the same deterministic order already
    # passed into json_writer.assemble_chapter_json below -- so registry
    # population never introduces its own ordering.
    #
    # C0.1 audit-findings refinement (Task 1): `topics` is now also a
    # first-class registry (TopicRegistry) here, populated from a
    # canonical-enveloped snapshot copy of `topics_out`, not `topics_out`
    # itself -- see the comment right above `registry_manager =` below and
    # compiler/registries.py's own "TOPIC REGISTRY" docstring section for
    # why a copy, not a shared reference, is used only for this one type.
    #
    # This is purely an INTERNAL compiler representation for this Phase B1
    # milestone: registry_manager is not attached to chapter_dict, not
    # written into the Chapter JSON -- the compiler continues to build the
    # Chapter JSON exactly as before this integration point. It IS,
    # however (B1 refinement pass), handed to compiler/state.py's
    # set_current_registry_manager() right below, so it survives past the
    # end of this function as the compiler's current-compilation-state
    # rather than simply falling out of scope -- see compiler/state.py's
    # module docstring for the full ownership/lifecycle contract. Later
    # Phase B milestones (registry enrichment, cross-link resolution,
    # Knowledge Graph construction, ...) are what will actually consume
    # it via compiler.get_current_registry_manager(); populating and
    # retaining it here now is what makes the registries "the
    # authoritative source for all later compiler phases" per the Phase
    # B1 task objective, without yet changing pipeline.py's output
    # contract.
    # C0.1 audit-findings refinement (Task 1): `topics_out` itself is
    # deliberately left untouched (it is what json_writer.assemble_chapter_json
    # serializes below, byte-for-byte unchanged by this refinement -- see
    # compiler/registries.py's own "TOPIC REGISTRY" docstring section for
    # the full reasoning). What TopicRegistry receives instead is a
    # separate, canonical-enveloped SNAPSHOT COPY of each topic -- built
    # the exact same way concepts/glossary build their own envelope
    # in-loop above (canonical.canonical_fields(), object_type="topic") --
    # so later phases (B1b enrichment / B1c normalization / B2 references /
    # B4 validation), which mutate registry items in place, only ever
    # mutate this snapshot, never `topics_out`/Chapter JSON.
    topic_registry_items: List[Dict[str, Any]] = [
        {
            **canonical.canonical_fields(
                object_id=t["id"], object_type="topic", namespace=canonical_namespace,
                urn_parts=["topic", t["id"]], subject=structure.subject,
                chapter_reference=chapter_reference, topic_ids=[],
                concept_ids=list(t.get("concepts") or []),
                source_page=t.get("page_start"), source_heading=t.get("title"),
                extraction_stage="pipeline.process_chapter:topic_registry_snapshot",
                extraction_method="deterministic", confidence=t.get("confidence", 0.5),
            ),
            "title": t.get("title"), "numbering": t.get("numbering"), "level": t.get("level"),
            "parent": t.get("parent"), "children": list(t.get("children") or []),
            "page_start": t.get("page_start"), "page_end": t.get("page_end"),
            "concepts": list(t.get("concepts") or []),
            "concept_names": list(t.get("concept_names") or []),
        }
        for t in topics_out
    ]
    registry_manager = create_registry_manager()
    populate_registries(
        registry_manager,
        topics=topic_registry_items,
        concepts=all_concepts, definitions=definitions, glossary=glossary,
        figures=figures, diagrams=diagrams, tables=tables, equations=equations,
        activities=activities, boxes=boxes, warnings=warnings_list, notes=notes,
        examples=examples,
    )
    # ---- Phase B1b: canonical registry enrichment -----------------------
    # Adds deterministic educational metadata (canonical_display_name,
    # normalized_name, educational_role, object_subtype, semantic_summary,
    # visual_summary, educational_importance/difficulty, extraction_quality,
    # registry_metadata, and -- where the object already carries one -- an
    # aliases list) onto every item already inserted above. See
    # compiler/enrichment.py's module docstring for the full field list,
    # derivation rules, and why this runs exactly here: registry items are
    # the SAME dict objects as all_concepts/figures/tables/... (populate_registries()
    # inserts references, never copies), so enriching them here also makes
    # these fields visible on the objects assemble_chapter_json() serializes
    # below -- additively only (new keys; no existing key/value/id/urn is
    # ever changed), so existing JSON output stays fully backward
    # compatible. Runs before set_current_registry_manager() so the
    # manager any later phase reads via compiler.get_current_registry_manager()
    # is always the enriched one, never a pre-enrichment snapshot.
    enrich_registries(registry_manager)
    # ---- Phase B1c: canonical normalization layer -----------------------
    # Adds deterministic lookup-key/alias-normalization metadata
    # (canonical_lookup_key, canonical_aliases, normalization) onto every
    # item already enriched above. See compiler/normalization.py's module
    # docstring for the full field list, derivation rules, and why this
    # runs exactly here: same "same dict objects, additive-only mutation"
    # reasoning as B1b's enrich_registries() call directly above -- this
    # is a second, independent additive pass over the same items, not a
    # redesign of enrichment. Runs after enrich_registries() (so
    # normalization can eventually be told apart from pre-normalization
    # enriched-only state via each item's own field set) and before
    # set_current_registry_manager() so the manager any later phase reads
    # via compiler.get_current_registry_manager() is always the fully
    # enriched-and-normalized one.
    normalize_registries(registry_manager)
    # ---- Phase B2: deterministic cross-reference resolution -------------
    # Resolves Definition/Glossary Entry -> Concept id links (and the
    # matching reverse definition_ids/glossary_ids/... lists on each
    # Concept record) using ONLY canonical ids, B1c's already-computed
    # normalized lookup keys/aliases, and deterministic registry lookups
    # -- see compiler/references.py's module docstring for the full
    # resolution strategy, why the other ten registries' concept_ids
    # stay [] today (no deterministic source field exists for them yet),
    # and why Topic -> Concept resolution (already correctly resolved in
    # the Phase A topic-construction loop above, into `concepts`/
    # `concept_names`) is verified here read-only rather than re-written.
    # Same "same dict objects, additive-only mutation" integration
    # pattern as B1b's enrich_registries() / B1c's normalize_registries()
    # directly above -- a third, independent additive pass over the same
    # items, not a redesign of either. Runs after normalize_registries()
    # (so resolution can rely on canonical_lookup_key/canonical_aliases
    # already being present) and before set_current_registry_manager()
    # so the manager any later phase reads via
    # compiler.get_current_registry_manager() is always the fully
    # enriched-normalized-and-resolved one. `topics_out` is passed only
    # for the read-only Topic-vs-Concept parity check (see
    # compiler/references.py's verify_topic_references) -- topic dicts
    # themselves are never mutated by this call.
    reference_resolution_stats = resolve_references(registry_manager, topics=topics_out)
    # ---- Phase B3: canonical semantic relationship resolution -----------
    # Turns the references B2 just resolved (definition_id/glossary_id's
    # own concept_id, each item's own Phase-A topic_ids, and each topic's
    # own already-Phase-A-resolved `concepts` list) into explicit, typed
    # Relationship records (has_definition / explains / described_by /
    # contains / appears_in / belongs_to / uses_concept / illustrates /
    # teaches) -- see compiler/relationships.py's module docstring for
    # the full generation rules and its MOST IMPORTANT REQUIREMENT
    # section. Relationships are stored ONLY in their own dedicated
    # "relationships" registry on `registry_manager` (created here,
    # on-demand, by resolve_relationships() itself) -- an internal
    # compiler-IR artifact, exactly like every other registry above.
    # They are NEVER attached to concepts/definitions/.../chapter_dict
    # and NEVER reach json_writer.assemble_chapter_json's output (called
    # further below) -- Phase C is what will consume this registry
    # directly via compiler.state.get_current_registry_manager(), not the
    # Chapter JSON file. Runs after resolve_references() (so concept_id/
    # concept_ids/topic_ids are already present to read) and before
    # set_current_registry_manager() so the manager any later phase reads
    # is always the fully enriched-normalized-resolved-and-related one.
    relationship_resolution_stats = resolve_relationships(registry_manager, topics=topics_out)
    # ---- Phase B4: compiler validation & integrity pass ------------------
    # Read-only inspection of everything Phases A/B0/B1/B1b/B1c/B2/B3 just
    # built: registry integrity (unique ids/urns, duplicate lookup keys/
    # aliases), canonical object integrity (required fields present),
    # reference integrity (every concept_id/concept_ids/topic_ids/reverse-
    # aggregation field actually resolves), relationship integrity (every
    # relationship's source/target exist, type is valid, no duplicates/
    # orphans), compiler state integrity (every required registry present,
    # including "relationships"), and determinism validation (id/urn shape,
    # relationship id recomputation) -- see compiler/validation.py's module
    # docstring for the full rule set. Never repairs or regenerates
    # anything (task's own "Do NOT implement automatic repair").
    #
    # NOTE the deliberate `compiler_validation_report` name (NOT
    # `validation_report`): Stage E (above) already binds a
    # `validation_report` local variable -- the educational-object
    # duplicate/bare-arithmetic report that DOES flow into
    # assemble_chapter_json() below. Reusing that name here would
    # silently shadow it and, worse, would mean whichever report is
    # assigned last is what assemble_chapter_json() actually receives --
    # exactly the "relationships/validation leaking into Chapter JSON"
    # failure mode this whole phase must avoid. Keeping the two names
    # distinct is what keeps this compiler-only report out of Chapter
    # JSON's `validation_report` field.
    #
    # The resulting report becomes part of the compiler state via
    # compiler_state.set_current_validation_report() below instead --
    # an internal compiler diagnostic, never serialized into Chapter
    # JSON. Runs after resolve_relationships() (so the "relationships"
    # registry already exists and is fully populated to validate) and
    # before set_current_registry_manager() so it inspects
    # `registry_manager` exactly as it will be handed off as this
    # chapter's compiler IR.
    compiler_validation_report = validate_compiler_state(registry_manager, topics=topics_out)
    # ---- Phase B5.1: compiler manifest & statistics -----------------------
    # Deterministic metadata DESCRIBING the compiler build Phases A-B4 just
    # produced -- versions, per-registry/relationship counts, and the B4
    # validation verdict -- read entirely from `compiler_validation_report`
    # (just computed above) and `registry_manager`'s own cheap aggregate
    # accessors. See compiler/build.py's module docstring for the full
    # field list and reuse strategy. Never changes the compiler IR: neither
    # call below inserts into, updates, or removes from any registry, and
    # neither artifact is attached to chapter_dict or reaches
    # json_writer.assemble_chapter_json's output below -- exactly the same
    # "internal compiler diagnostic, never serialized into Chapter JSON"
    # treatment Phase B4's compiler_validation_report already gets just
    # above. `chapter_identifier` is `chapter_reference` (computed once,
    # earlier in this function, from the same deterministic
    # book_slug/chapter_slug pair every id/urn/chapter_reference for this
    # chapter already uses) -- reused, not recomputed.
    #
    # Runs after validate_compiler_state() (so there is a validation report
    # to read status/summaries from) and before
    # set_current_registry_manager() so the manifest/statistics describe
    # `registry_manager` exactly as it is about to become "current", not a
    # stale snapshot.
    compiler_manifest = generate_compiler_manifest(
        registry_manager, compiler_validation_report,
        chapter_identifier=chapter_reference,
    )
    compiler_statistics = generate_compiler_statistics(
        registry_manager, compiler_validation_report,
    )
    # ---- Phase B5.2: compiler fingerprints & readiness --------------------
    # Deterministic fingerprints (per-registry + one overall compiler
    # fingerprint) and a read-only readiness verdict, derived entirely from
    # `registry_manager` (via each registry's own serialize()), plus the
    # `compiler_manifest`/`compiler_statistics` just generated above and
    # `compiler_validation_report` from Phase B4 -- see compiler/
    # fingerprints.py's module docstring for the full derivation and
    # volatile-field-exclusion strategy. Never changes the compiler IR:
    # this call inserts into, updates, or removes from no registry, and
    # none of its three results are attached to chapter_dict or reach
    # json_writer.assemble_chapter_json's output below -- exactly the
    # same "internal compiler diagnostic, never serialized into Chapter
    # JSON" treatment Phase B4's/B5.1's own artifacts already get above.
    #
    # Runs after generate_compiler_manifest()/generate_compiler_statistics()
    # (so there is a manifest/statistics to fold into the compiler
    # fingerprint) and before set_current_registry_manager() so the
    # fingerprints/readiness report describe `registry_manager` exactly as
    # it is about to become "current", not a stale snapshot.
    compiler_fingerprint_results = generate_compiler_fingerprints(
        registry_manager,
        manifest=compiler_manifest,
        statistics=compiler_statistics,
        validation_report=compiler_validation_report,
    )
    compiler_registry_fingerprints = compiler_fingerprint_results["registry_fingerprints"]
    compiler_fingerprint = compiler_fingerprint_results["compiler_fingerprint"]
    compiler_readiness_report = compiler_fingerprint_results["readiness_report"]

    compiler_state.set_current_registry_manager(registry_manager)
    compiler_state.set_current_validation_report(compiler_validation_report)
    compiler_state.set_current_compiler_manifest(compiler_manifest)
    compiler_state.set_current_compiler_statistics(compiler_statistics)
    compiler_state.set_current_registry_fingerprints(compiler_registry_fingerprints)
    compiler_state.set_current_compiler_fingerprint(compiler_fingerprint)
    compiler_state.set_current_compiler_readiness_report(compiler_readiness_report)
    # ---- Phase B5.3: compiler finalization ---------------------------------
    # One deterministic Build Summary and one Final Compiler Status
    # (READY / READY_WITH_WARNINGS / FAILED), aggregating the manifest,
    # statistics, fingerprints, and readiness report already produced
    # above -- see compiler/finalize.py's module docstring for the full
    # aggregation strategy. Performs no new validation or readiness
    # checking of its own: the final status is derived only from
    # `compiler_validation_report` (Phase B4) and `compiler_readiness_
    # report` (Phase B5.2). Never changes the compiler IR: this call
    # inserts into, updates, or removes from no registry, and neither of
    # its two results is attached to chapter_dict or reaches json_writer.
    # assemble_chapter_json's output below -- exactly the same "internal
    # compiler diagnostic, never serialized into Chapter JSON" treatment
    # every earlier Phase B artifact already gets above.
    #
    # Runs after generate_compiler_fingerprints() (so there is a
    # readiness report / compiler fingerprint to aggregate) and before the
    # compiler state for this chapter is considered complete.
    compiler_finalization = finalize_compiler_build(
        registry_manager,
        validation_report=compiler_validation_report,
        manifest=compiler_manifest,
        statistics=compiler_statistics,
        registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        readiness_report=compiler_readiness_report,
    )
    compiler_state.set_current_compiler_build_summary(compiler_finalization["build_summary"])
    compiler_state.set_current_final_compiler_status(compiler_finalization["final_status"])
    # ---- Phase C1: Knowledge Graph node construction -----------------------
    # The one Task 6 integration point: Knowledge Graph node construction
    # runs after Phase B is fully complete (the compiler build summary/
    # final status above are the last things Phase B computes for this
    # chapter) and reads ONLY the now-finished `registry_manager` (Compiler
    # IR) built above -- see knowledge_graph/build_nodes.py's own module
    # docstring for exactly what this does (one GraphNodeBase per canonical
    # object, zero edges). `graph_namespace=chapter_reference` reuses the
    # same deterministic "<book_slug>:<chapter_slug>" pair every id/urn for
    # this chapter already uses (see the `chapter_reference` comment
    # earlier in this function) rather than computing a second namespace.
    #
    # Never mutates `registry_manager` or any Compiler IR item inside it,
    # never touches chapter_dict, and never reaches json_writer.
    # assemble_chapter_json's output below -- Compiler IR and Educational
    # JSON are both unchanged by this call, exactly like every Phase B5
    # artifact above. Stored via knowledge_graph.state (mirroring
    # compiler_state's own per-chapter "set current, read later" pattern)
    # rather than compiler_state itself, since this is a distinct,
    # Knowledge-Graph-layer artifact -- see knowledge_graph/schema.py's own
    # docstring, which already anticipates `KnowledgeGraph.nodes` being
    # populated with a GraphRegistryManager instance by a future C1 phase.
    kg_state.reset_knowledge_graph_state()
    knowledge_graph_registry_manager = build_knowledge_graph_nodes(
        registry_manager, graph_namespace=chapter_reference,
    )
    # ---- Phase C2: Knowledge Graph edge construction -----------------------
    # The one Task 6 integration point: runs immediately after Phase C1
    # node construction above, into the SAME `knowledge_graph_registry_
    # manager` (never a fresh one -- edges reference node ids that must
    # already exist in its `nodes` registry) -- see
    # knowledge_graph/build_edges.py's own module docstring for exactly
    # what this does (one GraphEdgeBase per Compiler IR relationship,
    # read from `registry_manager`'s own "relationships" registry, which
    # `resolve_relationships()` already populated earlier in this same
    # function -- see that call site above). `graph_namespace=
    # chapter_reference` reuses the exact same namespace the Phase C1
    # call above already used, so every node id an edge references here
    # matches, byte-for-byte, the node id Phase C1 already built it
    # under.
    #
    # Never mutates `registry_manager`, any Compiler IR item inside it,
    # or the `nodes` registry Phase C1 already populated, and never
    # touches chapter_dict or json_writer.assemble_chapter_json's output
    # below -- Compiler IR and Educational JSON are both unchanged by
    # this call, exactly like the Phase C1 call above.
    knowledge_graph_registry_manager = build_knowledge_graph_edges(
        registry_manager, knowledge_graph_registry_manager,
        graph_namespace=chapter_reference,
    )
    knowledge_graph = KnowledgeGraph(
        metadata=KnowledgeGraphMetadata(
            graph_id=kg_graph_id(chapter_reference),
            graph_urn=kg_graph_urn(chapter_reference),
            source_chapter_identifier=chapter_reference,
            source_compiler_version=compiler_manifest.get("compiler_version"),
        ),
        nodes=knowledge_graph_registry_manager,
        edges=knowledge_graph_registry_manager,
    )
    kg_state.set_current_knowledge_graph(knowledge_graph)
    # ---- Phase C3: Knowledge Graph validation & integrity ------------------
    # The one Task 8 integration point: runs immediately after Phase C2
    # edge construction above completes (so there is a fully-populated
    # node AND edge registry to validate) -- see
    # knowledge_graph/validation.py's own validate_knowledge_graph()
    # docstring for exactly what this does (registry/node/edge/graph
    # integrity + determinism, folded into one
    # KnowledgeGraphValidationReport, returned as a plain dict). Passing
    # `registry_manager` (Compiler IR, already fully built by Phase B
    # above) as `compiler_registry_manager` enables the optional
    # cross-checks Task 1 allows "if required for verification only"
    # (compiler-object reference resolution, expected node/edge counts) --
    # read-only there too, exactly like the Phase C1/C2 calls above.
    #
    # Read-only over `knowledge_graph_registry_manager` and
    # `registry_manager`: never mutates either, never touches chapter_dict
    # or json_writer.assemble_chapter_json's output below -- Compiler IR,
    # Knowledge Graph nodes/edges, and Educational JSON are all unchanged
    # by this call, exactly like the Phase C1/C2 calls above. Stored via
    # knowledge_graph.state (mirroring compiler_state.
    # set_current_validation_report()'s own "current chapter's report"
    # pattern one layer up).
    knowledge_graph_validation_report = validate_knowledge_graph(
        knowledge_graph_registry_manager, compiler_registry_manager=registry_manager,
    )
    kg_state.set_current_knowledge_graph_validation_report(knowledge_graph_validation_report)
    # ---- Phase C4.1: Knowledge Graph Manifest & Statistics -----------------
    # The one Task 6 integration point: runs immediately after Phase C3
    # validation above completes (so `knowledge_graph_validation_report`
    # is available to read counts/summaries from) -- see
    # knowledge_graph/build.py's own module docstring for exactly what
    # this does (a small identity/versioning manifest + a larger
    # descriptive statistics breakdown, both derived from the C3 report
    # already computed above, plus one bounded pass over the node
    # registry for the one count C3 doesn't already track). Read-only
    # over `knowledge_graph_registry_manager` and `knowledge_graph.
    # metadata`: never mutates either, never touches chapter_dict or
    # json_writer.assemble_chapter_json's output below -- Compiler IR,
    # Knowledge Graph nodes/edges, and Educational JSON are all unchanged
    # by this call, exactly like the Phase C1/C2/C3 calls above. Stored
    # via knowledge_graph.state (mirroring compiler_state.
    # set_current_compiler_manifest()/set_current_compiler_statistics()'s
    # own "current chapter's artifacts" pattern one layer up).
    knowledge_graph_manifest = generate_knowledge_graph_manifest(
        knowledge_graph_registry_manager, knowledge_graph_validation_report,
        knowledge_graph.metadata,
    )
    knowledge_graph_statistics = generate_knowledge_graph_statistics(
        knowledge_graph_registry_manager, knowledge_graph_validation_report,
    )
    kg_state.set_current_knowledge_graph_manifest(knowledge_graph_manifest)
    kg_state.set_current_knowledge_graph_statistics(knowledge_graph_statistics)
    # ---- Phase C4.2: Knowledge Graph Fingerprints & Readiness --------------
    # The one Task 7 integration point: runs immediately after Phase C4.1
    # manifest/statistics generation above completes (so there is a
    # manifest/statistics to fold into the graph fingerprint) and before
    # any future Phase C4.3 logic -- see knowledge_graph/fingerprints.py's
    # own module docstring for exactly what this does (per-registry
    # fingerprints + one overall graph fingerprint + a read-only readiness
    # verdict, all derived from `knowledge_graph_registry_manager`, the
    # C4.1 manifest/statistics just generated above, and the Phase C3
    # validation report). Read-only over `knowledge_graph_registry_
    # manager`: never mutates it, never touches chapter_dict or
    # json_writer.assemble_chapter_json's output below -- Compiler IR,
    # Knowledge Graph nodes/edges, and Educational JSON are all unchanged
    # by this call, exactly like the Phase C1/C2/C3/C4.1 calls above.
    # Stored via knowledge_graph.state (mirroring compiler_state.
    # set_current_registry_fingerprints()/set_current_compiler_
    # fingerprint()/set_current_compiler_readiness_report()'s own "current
    # chapter's artifacts" pattern one layer down).
    knowledge_graph_fingerprint_results = generate_graph_fingerprints(
        knowledge_graph_registry_manager,
        manifest=knowledge_graph_manifest,
        statistics=knowledge_graph_statistics,
        validation_report=knowledge_graph_validation_report,
    )
    knowledge_graph_registry_fingerprints = knowledge_graph_fingerprint_results["registry_fingerprints"]
    knowledge_graph_fingerprint = knowledge_graph_fingerprint_results["graph_fingerprint"]
    knowledge_graph_readiness_report = knowledge_graph_fingerprint_results["readiness_report"]

    kg_state.set_current_registry_fingerprints(knowledge_graph_registry_fingerprints)
    kg_state.set_current_graph_fingerprint(knowledge_graph_fingerprint)
    kg_state.set_current_knowledge_graph_readiness_report(knowledge_graph_readiness_report)
    # ---- Phase C4.3: Knowledge Graph Finalization --------------------------
    # The one integration point: runs immediately after Phase C4.2
    # fingerprints/readiness above completes (so there is a readiness
    # report / graph fingerprint to aggregate) -- see
    # knowledge_graph/finalize.py's own module docstring for exactly what
    # this does (one deterministic Knowledge Graph Build Summary + one
    # Final Graph Status (READY / READY_WITH_WARNINGS / FAILED),
    # aggregating the manifest, statistics, fingerprints, and readiness
    # report already produced above). Performs no new validation or
    # readiness checking of its own: the final status is derived only
    # from `knowledge_graph_validation_report` (Phase C3) and
    # `knowledge_graph_readiness_report` (Phase C4.2). Never changes the
    # Knowledge Graph: this call inserts into, updates, or removes from
    # no graph registry, and neither of its two results is attached to
    # chapter_dict or reaches json_writer.assemble_chapter_json's output
    # below -- exactly the same "internal diagnostic, never serialized
    # into Chapter JSON" treatment every earlier Phase C artifact already
    # gets above. Stored via knowledge_graph.state (mirroring
    # compiler_state.set_current_compiler_build_summary()/
    # set_current_final_compiler_status()'s own "current chapter's
    # artifacts" pattern one layer down).
    knowledge_graph_finalization = finalize_knowledge_graph(
        knowledge_graph_registry_manager,
        validation_report=knowledge_graph_validation_report,
        manifest=knowledge_graph_manifest,
        statistics=knowledge_graph_statistics,
        registry_fingerprints=knowledge_graph_registry_fingerprints,
        graph_fingerprint=knowledge_graph_fingerprint,
        readiness_report=knowledge_graph_readiness_report,
    )
    kg_state.set_current_knowledge_graph_build_summary(
        knowledge_graph_finalization["graph_build_summary"]
    )
    kg_state.set_current_final_graph_status(
        knowledge_graph_finalization["graph_final_status"]
    )
    # ---- Phase D1: System Integrity Validation ------------------------------
    # The one Phase D1 integration point: runs after Phase C is fully
    # complete (knowledge_graph_finalization above is the last thing
    # Phase C computes for this chapter) -- see validation/
    # system_integrity.py's own module docstring for exactly what this
    # does (read-only cross-checks across the COMPLETE pipeline: Compiler
    # Registries <-> Knowledge Graph Nodes, Knowledge Graph Nodes <->
    # Knowledge Graph Edges, Compiler Fingerprints <-> Knowledge Graph
    # Fingerprints, Compiler Manifest <-> Knowledge Graph Manifest,
    # manifest counts <-> statistics counts on both layers, and readiness
    # reports/build summaries existing and agreeing with the fingerprints
    # already generated). This is NOT a second Compiler Validation or
    # Knowledge Graph Validation pass -- every check here either reads a
    # verdict either of those two passes (or the manifest/statistics/
    # fingerprints/readiness/build-summary passes downstream of them)
    # already computed, or performs one new check that genuinely spans
    # two artifacts neither existing pass has both of in scope.
    #
    # Read-only over every argument: no compiler registry and no graph
    # registry is inserted into, updated, or removed from; no manifest/
    # statistics/fingerprint/readiness-report/build-summary dict anywhere
    # is mutated; nothing here is attached to chapter_dict or reaches
    # json_writer.assemble_chapter_json's output below -- exactly the
    # same "internal diagnostic, never serialized into Chapter JSON"
    # treatment every Phase B5/Phase C artifact already gets above.
    # Stored via validation.state (mirroring compiler_state's/kg_state's
    # own "current chapter's artifacts" pattern one layer up).
    system_integrity_state.reset_system_integrity_state()
    system_integrity_report = validate_system_integrity(
        registry_manager, knowledge_graph_registry_manager,
        compiler_validation_report=compiler_validation_report,
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        compiler_registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_finalization["build_summary"],
        knowledge_graph_validation_report=knowledge_graph_validation_report,
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        knowledge_graph_registry_fingerprints=knowledge_graph_registry_fingerprints,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
    )
    system_integrity_state.set_current_system_integrity_report(system_integrity_report)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("chapter '%s': system integrity — status=%s errors=%d warnings=%d",
                     structure.chapter_title, system_integrity_report["overall_status"],
                     len(system_integrity_report["errors"]), len(system_integrity_report["warnings"]))
    # ---- Phase D2: Determinism & Reproducibility Validation ----------------
    # The one Phase D2 integration point: runs immediately after Phase D1
    # (system_integrity_report above is the last thing Phase D1 computes
    # for this chapter) -- see validation/determinism.py's own module
    # docstring for exactly what this does. This is NOT a second System
    # Integrity pass and does not re-check cross-artifact CONSISTENCY
    # (D1's job, already done above); it instead re-derives fingerprints/
    # re-serializes registries/re-canonicalizes manifests, statistics,
    # build summaries, and the D1 report itself, in-process, and confirms
    # each reproduces byte-identically -- proving REPRODUCIBILITY, not
    # correctness.
    #
    # Read-only over every argument: no compiler registry and no graph
    # registry is inserted into, updated, or removed from; no manifest/
    # statistics/fingerprint/build-summary/System-Integrity-Report dict
    # anywhere is mutated; nothing here is attached to chapter_dict or
    # reaches json_writer.assemble_chapter_json's output below -- same
    # "internal diagnostic, never serialized into Chapter JSON" treatment
    # system_integrity_report already gets above. Stored via validation.
    # determinism_state (mirroring validation.state's own "current
    # chapter's artifacts" pattern).
    determinism_state.reset_determinism_state()
    determinism_report = validate_determinism(
        registry_manager, knowledge_graph_registry_manager,
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        compiler_registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_build_summary=compiler_finalization["build_summary"],
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        knowledge_graph_registry_fingerprints=knowledge_graph_registry_fingerprints,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
        system_integrity_report=system_integrity_report,
    )
    determinism_state.set_current_determinism_report(determinism_report)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("chapter '%s': determinism — status=%s errors=%d warnings=%d",
                     structure.chapter_title, determinism_report["overall_status"],
                     len(determinism_report["errors"]), len(determinism_report["warnings"]))
    # ---- Phase D3: Release Readiness (Final Release Gate) -------------------
    # The one Phase D3 integration point: runs immediately after Phase D2
    # (determinism_report above is the last thing Phase D2 computes for
    # this chapter) -- see validation/release.py's own module docstring
    # for exactly what this does. This is NOT a third validation or
    # determinism pass and does not re-check anything D1/D2 (or any
    # earlier phase) already checked; it instead AGGREGATES every
    # already-computed Phase B-D2 report into one final Release
    # Readiness Report and one final Release Decision (READY /
    # READY_WITH_WARNINGS / FAILED).
    #
    # Read-only over every argument: no compiler registry and no graph
    # registry is inserted into, updated, or removed from; no manifest/
    # statistics/fingerprint/readiness-report/build-summary/validation-
    # report/System-Integrity-Report/Determinism-Report dict anywhere is
    # mutated; nothing here is attached to chapter_dict or reaches
    # json_writer.assemble_chapter_json's output below -- same "internal
    # diagnostic, never serialized into Chapter JSON" treatment
    # determinism_report already gets above. Stored via validation.
    # release_state (mirroring validation.state's/validation.
    # determinism_state's own "current chapter's artifacts" pattern one
    # artifact over).
    release_state.reset_release_state()
    release_finalization = finalize_release(
        compiler_validation_report=compiler_validation_report,
        knowledge_graph_validation_report=knowledge_graph_validation_report,
        compiler_readiness_report=compiler_readiness_report,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        compiler_build_summary=compiler_finalization["build_summary"],
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
        system_integrity_report=system_integrity_report,
        determinism_report=determinism_report,
        compiler_manifest=compiler_manifest,
        knowledge_graph_manifest=knowledge_graph_manifest,
        compiler_fingerprint=compiler_fingerprint,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        compiler_statistics=compiler_statistics,
        knowledge_graph_statistics=knowledge_graph_statistics,
    )
    release_state.set_current_release_readiness_report(
        release_finalization["release_readiness_report"]
    )
    release_state.set_current_release_status(release_finalization["release_status"])
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("chapter '%s': release readiness — status=%s errors=%d warnings=%d",
                     structure.chapter_title, release_finalization["release_status"],
                     len(release_finalization["release_readiness_report"]["errors"]),
                     len(release_finalization["release_readiness_report"]["warnings"]))
    # ---- Phase E1: Build Metadata --------------------------------------------
    # The one Phase E1 integration point: runs immediately after Phase D3
    # (release_finalization above is the last thing Phase D3 computes for
    # this chapter) and is the LAST artifact computed before Chapter JSON
    # is assembled below. This is NOT a fourth validation/determinism/
    # readiness pass and does not re-check anything any earlier phase
    # already checked; it instead AGGREGATES every already-computed
    # Phase B-D3 artifact, plus this chapter's own operational
    # (CompilationMetadata) and deterministic-configuration
    # (ConfigurationMetadata/VersionMetadata) details, into one
    # BuildMetadata record.
    #
    # Read-only over every argument: no compiler registry and no graph
    # registry is inserted into, updated, or removed from; no manifest/
    # statistics/fingerprint/readiness-report/build-summary/validation-
    # report/System-Integrity-Report/Determinism-Report/Release-
    # Readiness-Report anywhere is mutated; nothing here is attached to
    # chapter_dict or reaches json_writer.assemble_chapter_json's output
    # below -- same "internal diagnostic, never serialized into Chapter
    # JSON" treatment release_finalization already gets above. Stored via
    # build_metadata.state (mirroring validation.release_state's own
    # "current chapter's artifact" pattern one artifact over).
    build_metadata_state.reset_build_metadata_state()
    build_metadata_result = finalize_build_metadata(
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        compiler_registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_finalization["build_summary"],
        final_compiler_status=compiler_finalization["final_status"],
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        knowledge_graph_registry_fingerprints=knowledge_graph_registry_fingerprints,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
        final_graph_status=knowledge_graph_finalization["graph_final_status"],
        release_status=release_finalization["release_status"],
        pdf_path=pdf_path,
        compilation_start=datetime.fromtimestamp(t0, tz=timezone.utc),
        compilation_end=datetime.now(timezone.utc),
        processing_time_seconds=extraction_logs["processing_time"],
        use_vlm=use_vlm,
        page_batch_size=page_batch_size,
        force=force,
    )
    build_metadata_state.set_current_build_metadata(build_metadata_result["build_metadata"])
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("chapter '%s': build metadata — compiler_fingerprint=%s graph_fingerprint=%s "
                     "configuration_fingerprint=%s",
                     structure.chapter_title, compiler_fingerprint, knowledge_graph_fingerprint,
                     build_metadata_result["build_metadata"]["configuration_metadata"]["configuration_fingerprint"])
    # ---- Phase E2: Build Dependency Graph ------------------------------------
    # The one Phase E2 integration point: runs immediately after Phase E1
    # (build_metadata_result above is the last thing Phase E1 computes
    # for this chapter) and is the LAST artifact computed before Chapter
    # JSON is assembled below. This is NOT a fifth validation/
    # determinism/readiness pass and does not re-check anything any
    # earlier phase already checked; it instead DESCRIBES the build
    # dependencies between every already-computed Phase B-E1 artifact --
    # see dependency_graph/build.py's own module docstring for the exact
    # shape it encodes.
    #
    # Read-only over every argument: no compiler registry and no graph
    # registry is inserted into, updated, or removed from; no manifest/
    # statistics/fingerprint/readiness-report/build-summary/Release-
    # Readiness-Report/BuildMetadata dict anywhere is mutated; nothing
    # here is attached to chapter_dict or reaches
    # json_writer.assemble_chapter_json's output below -- same "internal
    # diagnostic, never serialized into Chapter JSON" treatment
    # build_metadata_result already gets above. `namespace=
    # chapter_reference` reuses the exact same namespace already used to
    # build this chapter's Knowledge Graph graph_id/graph_urn earlier in
    # this function, rather than computing a second one. Stored via
    # dependency_graph.state (mirroring build_metadata.state's own
    # "current chapter's artifact" pattern one artifact over).
    dependency_graph_state.reset_dependency_graph_state()
    dependency_graph_result = generate_dependency_graph(
        namespace=chapter_reference,
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        compiler_registry_fingerprints=compiler_registry_fingerprints,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_finalization["build_summary"],
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        knowledge_graph_registry_fingerprints=knowledge_graph_registry_fingerprints,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
        release_readiness_report=release_finalization["release_readiness_report"],
        build_metadata=build_metadata_result["build_metadata"],
    )
    dependency_graph_state.set_current_dependency_graph(
        dependency_graph_result["dependency_graph"]
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': dependency graph — nodes=%d edges=%d",
            structure.chapter_title,
            dependency_graph_result["dependency_graph"]["metadata"]["node_count"],
            dependency_graph_result["dependency_graph"]["metadata"]["edge_count"],
        )
    # ---- Phase E3: Change Detection -------------------------------------------
    # The one Phase E3 integration point: runs immediately after Phase E2
    # (dependency_graph_result above is the last thing Phase E2 computes
    # for this chapter) and is now the LAST artifact computed before
    # Chapter JSON is assembled below. This does NOT rebuild anything and
    # does NOT decide what should be rebuilt (that is Phase E4's
    # Incremental Compilation, not this integration point's concern) --
    # it only compares this chapter's current build against a previous
    # build's fingerprint snapshot and reports what changed. See
    # change_detection/engine.py's own module docstring for the exact
    # shape it encodes.
    #
    # `previous_build=None`: this codebase has no persistence layer yet
    # (explicitly out of Phase E3's own scope -- see change_detection/
    # __init__.py's own "NO PERSISTENCE" note), so there is currently no
    # source for a previous run's snapshot to pass in here. Every
    # artifact this chapter's build produces is therefore reported as
    # "added" until a future, out-of-scope phase supplies a real
    # `previous_build` (shaped exactly like this call's own
    # `current_build_snapshot` return value -- see change_detection/
    # snapshot.py's own module docstring) at this same call site.
    #
    # Read-only over every argument: no compiler registry, graph
    # registry, or dependency-graph registry is inserted into, updated,
    # or removed from; no manifest/statistics/fingerprint/readiness-
    # report/build-summary/BuildMetadata/DependencyGraph dict anywhere is
    # mutated; nothing here is attached to chapter_dict or reaches
    # json_writer.assemble_chapter_json's output below -- same "internal
    # diagnostic, never serialized into Chapter JSON" treatment
    # dependency_graph_result already gets above. `namespace=
    # chapter_reference` reuses the exact same namespace already used to
    # build this chapter's Knowledge Graph and Dependency Graph
    # graph_id/graph_urn earlier in this function, rather than computing
    # a second one. Stored via change_detection.state (mirroring
    # dependency_graph.state's own "current chapter's artifact" pattern
    # one artifact over).
    change_detection_state.reset_change_detection_state()
    change_detection_result = detect_changes(
        namespace=chapter_reference,
        dependency_graph=dependency_graph_result["dependency_graph"],
        build_metadata=build_metadata_result["build_metadata"],
        release_readiness_report=release_finalization["release_readiness_report"],
        previous_build=None,
    )
    change_detection_state.set_current_change_detection_report(
        change_detection_result["change_detection_report"]
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': change detection — added=%d removed=%d modified=%d "
            "affected=%d unchanged=%d",
            structure.chapter_title,
            change_detection_result["change_detection_report"]["summary"]["added_count"],
            change_detection_result["change_detection_report"]["summary"]["removed_count"],
            change_detection_result["change_detection_report"]["summary"]["modified_count"],
            change_detection_result["change_detection_report"]["summary"]["affected_count"],
            change_detection_result["change_detection_report"]["summary"]["unchanged_count"],
        )
    # ---- Phase E4: Incremental Compilation ------------------------------------
    # The one Phase E4 integration point: runs immediately after Phase E3
    # (change_detection_result above is the last thing Phase E3 computes
    # for this chapter) and is now the LAST artifact computed before
    # Chapter JSON is assembled below -- placed after E3 and before Phase
    # E5 (Validation & Finalization of this plan, not yet implemented), per
    # this integration point's own placement rule. This does NOT execute
    # any rebuild, does NOT cache anything, and does NOT decide to skip a
    # build step on its own -- it only reads Phase E3's own
    # ChangeDetectionReport and Phase E2's own DependencyGraph and reports
    # which artifacts a rebuild would need to touch, in what order. See
    # incremental_compilation/engine.py's own module docstring for the
    # exact shape it encodes.
    #
    # Read-only over every argument: no compiler registry, graph registry,
    # or dependency-graph registry is inserted into, updated, or removed
    # from; no manifest/statistics/fingerprint/readiness-report/build-
    # summary/BuildMetadata/DependencyGraph/ChangeDetectionReport dict
    # anywhere is mutated; nothing here is attached to chapter_dict or
    # reaches json_writer.assemble_chapter_json's output below -- same
    # "internal diagnostic, never serialized into Chapter JSON" treatment
    # change_detection_result already gets above. `namespace=
    # chapter_reference` reuses the exact same namespace already used to
    # build this chapter's Knowledge Graph, Dependency Graph, and Change
    # Detection Report graph_id/graph_urn/namespace earlier in this
    # function, rather than computing a second one. Stored via
    # incremental_compilation.state (mirroring change_detection.state's
    # own "current chapter's artifact" pattern one artifact over).
    incremental_compilation_state.reset_incremental_compilation_state()
    incremental_compilation_result = plan_incremental_compilation(
        namespace=chapter_reference,
        change_detection_report=change_detection_result["change_detection_report"],
        dependency_graph=dependency_graph_result["dependency_graph"],
        build_metadata=build_metadata_result["build_metadata"],
    )
    incremental_compilation_state.set_current_incremental_compilation_plan(
        incremental_compilation_result["incremental_compilation_plan"]
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': incremental compilation — dirty=%d affected=%d "
            "rebuild=%d clean=%d removed=%d",
            structure.chapter_title,
            incremental_compilation_result["incremental_compilation_plan"]["summary"]["dirty_count"],
            incremental_compilation_result["incremental_compilation_plan"]["summary"]["affected_count"],
            incremental_compilation_result["incremental_compilation_plan"]["summary"]["rebuild_count"],
            incremental_compilation_result["incremental_compilation_plan"]["summary"]["clean_count"],
            incremental_compilation_result["incremental_compilation_plan"]["summary"]["removed_count"],
        )
    # ---- Phase E5.1: Incremental Compilation Validation -----------------------
    # The one Phase E5.1 integration point: runs immediately after Phase E4
    # (incremental_compilation_result above is the last thing Phase E4
    # computes for this chapter) and is now the LAST artifact computed
    # before Chapter JSON is assembled below -- placed after E4 and before
    # Phase E5.2 (Incremental Compilation Finalization, not yet
    # implemented), per this integration point's own placement rule. This
    # does NOT execute any rebuild, does NOT modify the rebuild plan, and
    # does NOT generate readiness / final status / a build summary (Phase
    # E5.2's own job) -- it only validates Phase E4's own
    # IncrementalCompilationPlan against itself and against Phase E2's own
    # DependencyGraph, and reports what it finds. See
    # incremental_compilation_validation/engine.py's own module docstring
    # for the exact shape it encodes.
    #
    # Read-only over every argument: no compiler registry, graph registry,
    # or dependency-graph registry is inserted into, updated, or removed
    # from; no manifest/statistics/fingerprint/readiness-report/build-
    # summary/BuildMetadata/DependencyGraph/ChangeDetectionReport/
    # IncrementalCompilationPlan dict anywhere is mutated (confirmed by
    # this call's own read-only-behaviour check); nothing here is attached
    # to chapter_dict or reaches json_writer.assemble_chapter_json's output
    # below -- same "internal diagnostic, never serialized into Chapter
    # JSON" treatment incremental_compilation_result already gets above.
    # `namespace=chapter_reference` reuses the exact same namespace already
    # used to build this chapter's Knowledge Graph, Dependency Graph,
    # Change Detection Report, and Incremental Compilation Plan
    # graph_id/graph_urn/namespace earlier in this function, rather than
    # computing a second one. Stored via incremental_compilation_validation.
    # state (mirroring incremental_compilation.state's own "current
    # chapter's artifact" pattern one artifact over).
    incremental_compilation_validation_state.reset_incremental_compilation_validation_state()
    incremental_compilation_validation_result = validate_incremental_compilation(
        namespace=chapter_reference,
        incremental_compilation_plan=incremental_compilation_result["incremental_compilation_plan"],
        dependency_graph=dependency_graph_result["dependency_graph"],
        change_detection_report=change_detection_result["change_detection_report"],
    )
    incremental_compilation_validation_state.set_current_incremental_compilation_validation_report(
        incremental_compilation_validation_result["incremental_compilation_validation_report"]
    )
    incremental_compilation_validation_state.set_current_incremental_compilation_validation_status(
        incremental_compilation_validation_result["incremental_compilation_validation_report"]["overall_status"]
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': incremental compilation validation — status=%s "
            "passed=%d failed=%d errors=%d warnings=%d",
            structure.chapter_title,
            incremental_compilation_validation_result["incremental_compilation_validation_report"]["overall_status"],
            len(incremental_compilation_validation_result["incremental_compilation_validation_report"]["checks_passed"]),
            len(incremental_compilation_validation_result["incremental_compilation_validation_report"]["checks_failed"]),
            len(incremental_compilation_validation_result["incremental_compilation_validation_report"]["errors"]),
            len(incremental_compilation_validation_result["incremental_compilation_validation_report"]["warnings"]),
        )
    # ---- Phase E5.2: Incremental Compilation Finalization ----------------------
    # The one Phase E5.2 integration point: runs immediately after Phase E5.1
    # (incremental_compilation_validation_result above is the last thing Phase
    # E5.1 computes for this chapter) and before any future Phase F. This does
    # NOT perform validation, does NOT perform planning, does NOT detect
    # changes, does NOT traverse the dependency graph, and does NOT rebuild
    # any compiler artifact -- it only aggregates Phase E4's own
    # IncrementalCompilationPlan and Phase E5.1's own
    # IncrementalCompilationValidationReport into one final Incremental
    # Compilation Final Status, one Readiness Report, and one Build Summary.
    # See incremental_compilation_finalization/finalize.py's own module
    # docstring for the exact decision rule and shape it encodes.
    #
    # Read-only over every argument: no compiler registry, graph registry, or
    # dependency-graph registry is inserted into, updated, or removed from;
    # no manifest/statistics/fingerprint/readiness-report/build-summary/
    # BuildMetadata/DependencyGraph/ChangeDetectionReport/
    # IncrementalCompilationPlan/IncrementalCompilationValidationReport dict
    # anywhere is mutated; nothing here is attached to chapter_dict or
    # reaches json_writer.assemble_chapter_json's output below -- same
    # "internal diagnostic, never serialized into Chapter JSON" treatment
    # incremental_compilation_validation_result already gets above.
    # `namespace=chapter_reference` reuses the exact same namespace already
    # used to build this chapter's Knowledge Graph, Dependency Graph, Change
    # Detection Report, Incremental Compilation Plan, and Incremental
    # Compilation Validation Report graph_id/graph_urn/namespace earlier in
    # this function, rather than computing a second one. Stored via
    # incremental_compilation_finalization.state (mirroring
    # incremental_compilation_validation.state's own "current chapter's
    # artifact" pattern one artifact over).
    incremental_compilation_finalization_state.reset_incremental_compilation_finalization_state()
    incremental_compilation_finalization_result = finalize_incremental_compilation(
        namespace=chapter_reference,
        incremental_compilation_plan=incremental_compilation_result["incremental_compilation_plan"],
        incremental_compilation_validation_report=incremental_compilation_validation_result["incremental_compilation_validation_report"],
        build_metadata=build_metadata_result["build_metadata"],
        dependency_graph=dependency_graph_result["dependency_graph"],
        change_detection_report=change_detection_result["change_detection_report"],
    )
    incremental_compilation_finalization_state.set_current_incremental_compilation_readiness_report(
        incremental_compilation_finalization_result["incremental_compilation_readiness_report"]
    )
    incremental_compilation_finalization_state.set_current_incremental_compilation_build_summary(
        incremental_compilation_finalization_result["incremental_compilation_build_summary"]
    )
    incremental_compilation_finalization_state.set_current_incremental_compilation_final_status(
        incremental_compilation_finalization_result["incremental_compilation_final_status"]
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': incremental compilation finalization — final_status=%s "
            "rebuild_targets=%d reused=%d warnings=%d errors=%d",
            structure.chapter_title,
            incremental_compilation_finalization_result["incremental_compilation_final_status"],
            incremental_compilation_finalization_result["incremental_compilation_build_summary"]["rebuild_target_count"],
            incremental_compilation_finalization_result["incremental_compilation_build_summary"]["reused_artifact_count"],
            incremental_compilation_finalization_result["incremental_compilation_build_summary"]["warning_count"],
            incremental_compilation_finalization_result["incremental_compilation_build_summary"]["error_count"],
        )
    # Diagnostic only, and deliberately guarded: RegistryStatistics.
    # approx_memory_bytes does a real (shallow) sys.getsizeof() scan over
    # every registry's contents (see registry.py's _estimate_memory_bytes),
    # so computing it unconditionally on every chapter run -- as an
    # earlier version of this integration point did, passing
    # registry_manager.statistics() directly as a logger.debug() argument
    # -- did that scan every run regardless of logging level (Python
    # evaluates call arguments eagerly; logger.debug()'s own laziness only
    # covers %-formatting, not argument construction). Gating on
    # isEnabledFor(DEBUG) first means this work is skipped entirely at
    # the INFO level this pipeline runs at by default -- no behavior
    # change to what gets logged when DEBUG *is* enabled, just no
    # unnecessary work when it isn't.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("chapter '%s': registry population — %s",
                     structure.chapter_title, registry_manager.statistics())
        logger.debug("chapter '%s': universal object linking — %s",
                     structure.chapter_title, topic_linking_stats)
        logger.debug("chapter '%s': reference resolution — %s",
                     structure.chapter_title, reference_resolution_stats)
        logger.debug("chapter '%s': relationship resolution — %s",
                     structure.chapter_title, relationship_resolution_stats)
        logger.debug("chapter '%s': compiler validation — status=%s errors=%d warnings=%d",
                     structure.chapter_title, compiler_validation_report["status"],
                     len(compiler_validation_report["errors"]), len(compiler_validation_report["warnings"]))
        logger.debug("chapter '%s': compiler manifest — %s",
                     structure.chapter_title, compiler_manifest)
        logger.debug("chapter '%s': compiler statistics — %s",
                     structure.chapter_title, compiler_statistics)
        logger.debug("chapter '%s': knowledge graph validation — status=%s errors=%d warnings=%d",
                     structure.chapter_title, knowledge_graph_validation_report["overall_status"],
                     len(knowledge_graph_validation_report["errors"]), len(knowledge_graph_validation_report["warnings"]))
        logger.debug("chapter '%s': knowledge graph manifest — %s",
                     structure.chapter_title, knowledge_graph_manifest)
        logger.debug("chapter '%s': knowledge graph statistics — %s",
                     structure.chapter_title, knowledge_graph_statistics)
        logger.debug("chapter '%s': knowledge graph fingerprint — %s",
                     structure.chapter_title, knowledge_graph_fingerprint)
        logger.debug("chapter '%s': knowledge graph readiness — ready=%s passed=%d failed=%d",
                     structure.chapter_title, knowledge_graph_readiness_report["ready"],
                     knowledge_graph_readiness_report["readiness_summary"]["passed_count"],
                     knowledge_graph_readiness_report["readiness_summary"]["failed_count"])

    chapter_dict = json_writer.assemble_chapter_json(
        structure=structure, pdf_path=pdf_path, topics_semantic=topics_out, concepts=all_concepts,
        glossary=glossary, definitions=definitions, examples=examples, activities=activities,
        figures=figures, tables=tables, equations=equations, diagrams=diagrams, charts=charts,
        graphs=graphs_, maps=maps_, timelines=timelines, boxes=boxes, notes=notes, warnings=warnings_list,
        learning_graph=learning_graph, concept_graph=concept_graph, semantic_index=semantic_index,
        ai_metadata=ai_metadata, generation_metadata=generation_metadata, quality=quality,
        extraction_logs=extraction_logs, ocr_engine_name=f"pymupdf_text_layer+tesseract_fallback (lang={structure.language})",
        vlm_model_id=VLM_MODEL_ID if use_vlm else "disabled",
        processing_time_seconds=extraction_logs["processing_time"],
        blocks=blocks, educational_objects=educational_objects, validation_report=validation_report,
    )

    # ---- Milestone 5.1: Document Structure Tree (DST) Pipeline Integration -
    # The one M5.1 integration point: runs immediately after `chapter_dict`
    # above is fully assembled -- `chapter_dict` IS "an already-completed
    # schemas.chapter_schema.ChapterJSON" (document_structure_tree.builder.
    # build_tree_from_chapter_json()'s own documented input contract), so
    # this is the first point in process_chapter() where that contract is
    # satisfied. Placed before `doc.close()`/`write_chapter_json()` so DST
    # construction happens as part of "successful chapter compilation"
    # itself, not after this chapter's own JSON has already been written to
    # disk. Mirrors the Phase C1-C4 Knowledge Graph integration block
    # earlier in this function in spirit (same "one compiler-owned artifact
    # built from this chapter's already-finished upstream state" shape,
    # architecture §6/§7), but is its own, independent step -- DST and the
    # Knowledge Graph never read from or feed into each other (see
    # document_structure_tree/__init__.py's own module docstring).
    #
    # Reuses Milestones 1-4 exactly as they already exist -- `build_tree_
    # from_chapter_json()` (the builder) and `generate_artifact()` (which
    # itself drives Milestone 3's frozen `run_all_invariants()` -- see
    # artifact.py's own docstring, "generate_artifact() calls validation.
    # run_all_invariants() exactly as Milestone 3 exposes it"). Nothing
    # here re-implements the builder or the validation engine.
    #
    # `chapter_dict` may already be a `ChapterJSON` instance or its
    # `model_dump()`-shaped dict, depending on json_writer.
    # assemble_chapter_json()'s own return convention -- accept either
    # rather than assuming one, so this integration point never silently
    # builds an empty tree from an object with no `.topics` attribute.
    #
    # `registry_manager` (Compiler IR, already fully built by Phase B
    # above and read read-only by every Phase C step already) is adapted
    # to the frozen `CanonicalRegistrySnapshot` Protocol via `document_
    # structure_tree.registry_snapshot.CompilerRegistrySnapshot` --
    # Milestone 5's own scaffolding for exactly this seam (see that
    # module's own docstring). `chapter_reference` is reused, unchanged,
    # as both the DST `ChapterId` and the `canonical_registry_snapshot_ref`
    # label -- the same deterministic "<book_slug>:<chapter_slug>" pair
    # every other artifact type in this chapter already uses as its own
    # chapter identifier (see the Phase C1 `KnowledgeGraphMetadata.
    # source_chapter_identifier`/compiler_manifest `chapter_identifier`
    # call sites above).
    #
    # FAILURE PROPAGATION: `build_tree_from_chapter_json()` raises
    # `DSTBuildError` and `generate_artifact()` raises `DSTArtifactError`
    # only for precondition failures -- a source structure (or a resulting
    # tree) that cannot be assembled into an artifact at all (e.g. two
    # topics sharing one source id, an unresolvable parent chain, an empty
    # tree) -- never for a tree that assembles cleanly but fails one or
    # more §15 invariants (that is `validation_status = "fail"`, a normal,
    # fully representable artifact state; see artifact.py's own "A NOTE ON
    # 'GENERATION' VS. 'VALIDATION OUTCOME'"). Only that first kind of
    # failure is caught here, and only to log it with full chapter context
    # before re-raising unchanged -- it is never swallowed. Re-raising lets
    # it reach process_all_pdfs()'s own per-PDF `except Exception` (near
    # the end of this file), which already logs and marks this one chapter
    # failed without stopping the rest of the book, exactly like every
    # other extraction failure in this pipeline.
    dst_state.reset_document_structure_tree_state()
    logger.info("chapter '%s': building Document Structure Tree", structure.chapter_title)
    try:
        chapter_json_for_dst = (
            chapter_dict
            if isinstance(chapter_dict, ChapterJSON)
            else ChapterJSON.model_validate(chapter_dict)
        )
        dst_chapter_id = ChapterId(chapter_reference)
        built_dst_tree = build_tree_from_chapter_json(dst_chapter_id, chapter_json_for_dst)
        dst_registry_snapshot = CompilerRegistrySnapshot(
            registry_manager=registry_manager, chapter_id=dst_chapter_id,
        )
        document_structure_tree = generate_artifact(
            tree=built_dst_tree.tree,
            chapter_id=dst_chapter_id,
            schema_version=DST_SCHEMA_VERSION,
            compiler_version=DST_COMPILER_VERSION,
            canonical_registry_snapshot_ref=chapter_reference,
            registry=dst_registry_snapshot,
        )
    except (DSTBuildError, DSTArtifactError, DSTValueError, DSTIdentityError,
            DSTSerializationError, DocumentStructureTreeError) as exc:
        logger.error(
            "chapter '%s': Document Structure Tree build failed: %s",
            structure.chapter_title, exc,
        )
        raise
    dst_state.set_current_document_structure_tree(document_structure_tree)
    dst_validation_status = document_structure_tree.validation_metadata.validation_status
    dst_failed_invariants = [
        result.invariant_id.value
        for result in document_structure_tree.validation_metadata.validation_results
        if result.status is not DSTValidationStatus.PASS
    ]
    if dst_validation_status is DSTValidationStatus.PASS:
        logger.info(
            "chapter '%s': Document Structure Tree — status=pass node_count=%d",
            structure.chapter_title, len(document_structure_tree.tree),
        )
    else:
        logger.warning(
            "chapter '%s': Document Structure Tree — status=fail failed_invariants=%s",
            structure.chapter_title, dst_failed_invariants,
        )

    # ---- Milestone 5.2: Document Structure Tree (DST) — Artifact
    # Registration & Persistence: build_metadata integration -----------------
    # NOT part of Milestone 5.1's own frozen block above (see this
    # milestone's own "Out of Scope: Pipeline integration from M5.1" --
    # nothing above this comment is touched). `build_metadata_result` was
    # already computed and stored by Phase E1 earlier in process_chapter()
    # (see the "Phase E1: Build Metadata" block above), before the DST
    # itself existed -- its `dst_metadata` sub-block is therefore still the
    # all-None default `generate_dst_metadata()` produces (see
    # build_metadata.build's own module docstring). Now that
    # `document_structure_tree` is available, this fills that block in via
    # `attach_dst_metadata()` (an immutable "return a new dict" update,
    # never a mutation of the dict Phase E1 already produced) and re-stores
    # the result in build_metadata.state, so both the in-memory
    # `build_metadata_result` used below and any later in-process reader of
    # `build_metadata.state.get_current_build_metadata()` see the same,
    # DST-aware BuildMetadata. Every value passed to `generate_dst_metadata()`
    # is read verbatim off `document_structure_tree` -- nothing here
    # recomputes fingerprinting, validation, or artifact assembly a second
    # time (Milestone 3/4's own `chapter_fingerprint`/`validation_status`
    # are reused exactly as Milestone 5.1 already computed them above).
    dst_metadata_block = generate_dst_metadata(
        document_structure_tree_artifact_metadata=document_structure_tree.artifact_metadata.to_json(),
        document_structure_tree_validation_metadata=document_structure_tree.validation_metadata.to_json(),
        dst_chapter_fingerprint=document_structure_tree.artifact_metadata.chapter_fingerprint.to_json(),
        dst_node_count=len(document_structure_tree.tree),
        final_dst_status=dst_validation_status.to_json(),
    )
    build_metadata_result["build_metadata"] = attach_dst_metadata(
        build_metadata_result["build_metadata"], dst_metadata=dst_metadata_block,
    )
    build_metadata_state.set_current_build_metadata(build_metadata_result["build_metadata"])
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chapter '%s': build metadata — dst_chapter_fingerprint=%s final_dst_status=%s",
            structure.chapter_title, dst_metadata_block["dst_chapter_fingerprint"],
            dst_metadata_block["final_dst_status"],
        )

    doc.close()
    out_path = json_writer.write_chapter_json(chapter_dict, structure.klass, structure.subject, book_slug,
                                               structure.chapter_number, structure.chapter_title,
                                               output_root=output_root)
    # ---- Phase 1 Output Persistence Enhancement -----------------------------
    # Purely additive: every artifact below was already fully computed by
    # Stage B-E1 above (nothing here recomputes, redesigns, or reorders
    # anything) -- this call site only decides that these already-existing,
    # previously in-memory-only outputs are now ALSO written to durable
    # storage, exactly like the Chapter JSON write immediately above it.
    # Never runs before write_chapter_json() (Stage A's own persisted
    # artifact is unaffected either way), and a failure here can never mask
    # or replace this chapter's real extraction outcome -- same "never
    # raises" contract CompilerRuntime._record_*() (Phase F2-F5) already
    # uses one layer up, applied here at chapter scope.
    _persist_phase1_artifacts(
        klass=structure.klass, subject=structure.subject, book_slug=book_slug,
        chapter_number=structure.chapter_number, chapter_title=structure.chapter_title,
        output_root=output_root,
        registry_manager=registry_manager,
        compiler_manifest=compiler_manifest,
        compiler_statistics=compiler_statistics,
        compiler_registry_fingerprints=compiler_registry_fingerprints,
        compiler_fingerprint=compiler_fingerprint,
        compiler_validation_report=compiler_validation_report,
        compiler_readiness_report=compiler_readiness_report,
        compiler_build_summary=compiler_finalization["build_summary"],
        final_compiler_status=compiler_finalization["final_status"],
        knowledge_graph_metadata=knowledge_graph.metadata,
        knowledge_graph_registry_manager=knowledge_graph_registry_manager,
        knowledge_graph_manifest=knowledge_graph_manifest,
        knowledge_graph_statistics=knowledge_graph_statistics,
        knowledge_graph_validation_report=knowledge_graph_validation_report,
        knowledge_graph_registry_fingerprints=knowledge_graph_registry_fingerprints,
        knowledge_graph_fingerprint=knowledge_graph_fingerprint,
        knowledge_graph_readiness_report=knowledge_graph_readiness_report,
        knowledge_graph_build_summary=knowledge_graph_finalization["graph_build_summary"],
        final_graph_status=knowledge_graph_finalization["graph_final_status"],
        system_integrity_report=system_integrity_report,
        determinism_report=determinism_report,
        release_readiness_report=release_finalization["release_readiness_report"],
        release_status=release_finalization["release_status"],
        build_metadata=build_metadata_result["build_metadata"],
        dependency_graph=dependency_graph_result["dependency_graph"],
        document_structure_tree=document_structure_tree,
        copyright_debug_entries=_copyright_debug_entries,
    )

    # ---- M6.3: Teacher Knowledge Base (TKB) Build -------------------------
    # Runs after all Phase 1 artifacts are sealed and persisted.
    # TKB Builder is a Phase 1 finalization stage (M6_ARCHITECTURE_SPECIFICATION §2).
    # Non-fatal: a TKB build failure never breaks the chapter JSON output.
    try:
        from teacher_knowledge_base.builder import build_teacher_knowledge_base
        from teacher_knowledge_base import state as tkb_state
        tkb_state.reset_all_tkb_state()

        # Assemble concept_index from knowledge_graph nodes.
        _tkb_concept_index: Dict[str, Any] = {}
        try:
            _kg_nodes = getattr(knowledge_graph, "nodes", None)
            if isinstance(_kg_nodes, dict):
                for _nid, _node in _kg_nodes.items():
                    _nd = _node if isinstance(_node, dict) else (
                        _node.__dict__ if hasattr(_node, "__dict__") else {}
                    )
                    _tkb_concept_index[_nid] = {
                        "concept_key": _nd.get("concept_key") or _nd.get("canonical_key") or "",
                        "name": _nd.get("name") or _nd.get("title") or _nid,
                        "title": _nd.get("name") or _nd.get("title") or _nid,
                        "description": _nd.get("description") or "",
                        "definition": _nd.get("definition") or _nd.get("description") or "",
                        "definition_confidence": float(_nd.get("confidence") or 0.9),
                        "prerequisites": _nd.get("prerequisites") or [],
                        "difficulty": _nd.get("difficulty") or "medium",
                        "importance": _nd.get("importance") or "core",
                        "estimated_teaching_time_minutes": float(
                            _nd.get("estimated_teaching_time_minutes") or 30.0
                        ),
                        "revision_notes": _nd.get("revision_notes") or [],
                        "learning_objectives_raw": _nd.get("learning_objectives") or [],
                    }
        except Exception as _tkb_ci_exc:
            logger.debug("TKB: concept_index extraction: %s", _tkb_ci_exc)

        _tkb_kg_dict: Dict[str, Any] = {}
        try:
            _tkb_kg_dict = (
                knowledge_graph.to_dict() if hasattr(knowledge_graph, "to_dict")
                else (knowledge_graph if isinstance(knowledge_graph, dict)
                      else getattr(knowledge_graph, "__dict__", {}))
            )
        except Exception:
            pass

        _tkb_dst_dict: Dict[str, Any] = {}
        try:
            if document_structure_tree is not None:
                _tkb_dst_dict = (
                    document_structure_tree.to_dict()
                    if hasattr(document_structure_tree, "to_dict")
                    else (document_structure_tree
                          if isinstance(document_structure_tree, dict)
                          else getattr(document_structure_tree, "__dict__", {}))
                )
        except Exception:
            pass

        _tkb_dep_edges: List[Any] = []
        try:
            _dg_data = dependency_graph_result.get("dependency_graph") or {}
            _raw_edges = (
                _dg_data.get("edges") or []
                if isinstance(_dg_data, dict)
                else getattr(_dg_data, "edges", []) or []
            )
            _tkb_dep_edges = [_e if isinstance(_e, dict) else {} for _e in _raw_edges]
        except Exception:
            pass

        _tkb_result = build_teacher_knowledge_base(
            config={
                "chapter_id": chapter_reference,
                "chapter_number": int(structure.chapter_number or 0),
                "chapter_title": str(structure.chapter_title or ""),
                "subject": str(structure.subject or ""),
                "book_title": str(
                    getattr(structure, "book_title", None) or book_slug or ""
                ),
                "klass": str(structure.klass or ""),
                "board": str(getattr(structure, "board", None) or ""),
                "source_artifact_id": chapter_reference,
                "strict_validation": False,
            },
            direct_artifacts={
                "optimized_knowledge_package": {
                    "concept_index": _tkb_concept_index,
                    "dependency_map": {"edges": _tkb_dep_edges},
                    "learning_analytics": {"concept_analytics": {
                        _cid: {
                            "difficulty": _info.get("difficulty", "medium"),
                            "importance": _info.get("importance", "core"),
                            "estimated_teaching_time_minutes": float(
                                _info.get("estimated_teaching_time_minutes", 30.0)
                            ),
                        }
                        for _cid, _info in _tkb_concept_index.items()
                    }},
                    "manifest": {"package_id": chapter_reference},
                },
                "document_structure_tree": _tkb_dst_dict,
                "knowledge_graph": _tkb_kg_dict,
            },
        )
        logger.info(
            "TKB build complete: tkb_id=%s concepts=%d validation=%s",
            _tkb_result.artifact.get_tkb_id(),
            _tkb_result.artifact.get_total_concepts(),
            (_tkb_result.artifact.to_dict().get("validation") or {}).get("status", "?"),
        )
    except Exception as _tkb_exc:
        logger.warning(
            "TKB build failed (non-fatal) for chapter %r: %s",
            chapter_reference,
            _tkb_exc,
        )

    return out_path


def process_all_pdfs(use_vlm: bool = True, page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE, force: bool = False,
                      pdf_folder: Optional[str] = None, output_root: Optional[str] = None,
                      book_title_override: Optional[str] = None,
                      cancel_check: Optional[Callable[[], bool]] = None,
                      book_index: Optional[int] = None, total_books: Optional[int] = None) -> Dict[str, Any]:
    """Processes every chapter PDF in a single folder (one book's worth of PDFs).

    `pdf_folder` defaults to the top-level PDF_INPUT_FOLDER, and `output_root`
    defaults to the top-level JSON_OUTPUT_FOLDER, preserving the original
    single-book behavior exactly (`python pipeline.py` with PDFs dropped
    directly into pdf_in/). book_orchestrator.py calls this once per
    discovered book subfolder, passing that subfolder as `pdf_folder`, a
    book-specific subfolder of JSON_OUTPUT_FOLDER as `output_root`, and the
    book subfolder's name as `book_title_override` so the folder name --
    not anything inferred from the PDFs -- becomes the book title (and
    therefore the `book_slug` directory json_writer groups that book's
    chapter JSONs under). Returns a small stats dict so a caller (e.g. the
    orchestrator) can report per-book results without re-deriving them from
    logs.

    `cancel_check` (Phase F1, runtime/runtime.py): an optional, zero-arg
    callable checked once before each chapter in the loop below; when it
    returns True, the remaining chapters in *this* folder are skipped and
    the returned stats dict carries `"cancelled": True`. Purely additive --
    defaults to None, in which case behavior is byte-for-byte identical to
    before this parameter existed (no check is ever performed). This is the
    only cooperative-cancellation checkpoint Phase F1's CompilerRuntime has
    available; it does not interrupt a chapter already in progress inside
    process_chapter(), only the gap between one chapter finishing and the
    next one starting.
    """
    pdf_folder = pdf_folder or PDF_INPUT_FOLDER
    os.makedirs(pdf_folder, exist_ok=True)
    # NOTE: no local os.makedirs() for the output side anymore -- chapter/
    # manifest output now lives on OneDrive (see modules/json_writer.py),
    # and json_writer.book_output_dir() provisions each book's
    # json_out/logs/cache/assets folders there automatically the first
    # time a chapter for that book is written.
    all_paths = sorted(glob.glob(os.path.join(pdf_folder, "*.pdf")))
    if not all_paths:
        logger.warning("No PDFs found in '%s'.", os.path.abspath(pdf_folder))
        return {"found": 0, "written": 0, "failed": 0}

    prelims_path = pdf_parser.find_prelims_pdf(all_paths)
    chapter_paths = [p for p in all_paths if p != prelims_path]
    if prelims_path:
        logger.info("Using prelims/TOC file: %s", os.path.basename(prelims_path))
    book_ctx = pdf_parser.load_book_context(prelims_path)
    if book_title_override:
        # Phase 1 Final Metadata Architecture Refinement (STEP 2/3):
        # book_ctx.book_folder_name is a BACKWARD-COMPATIBILITY override
        # only (see BookContext.book_folder_name's own docstring) -- it
        # must win over derived_storage_identity for books that have no
        # distinguishing cover metadata of their own (subtitle/Part/
        # Volume), because in that case the folder name is the ONLY
        # signal available to keep sibling books (e.g. "Part 1"/"Part 2"
        # folders of the same subject) from colliding in json_out/.
        #
        # It must NOT be set when the prelims/TOC PDF already gave us
        # distinguishing cover metadata -- doing so unconditionally (the
        # pre-refinement behavior) permanently shadows
        # derived_storage_identity for every single book, since
        # book_orchestrator.py always supplies a folder name for every
        # discovered book. That defeated the entire point of the
        # refinement: real NCERT runs kept writing to operator-named
        # folders like "Accountancy_Part_1" instead of the canonical
        # "Accountancy - Partnership Accounts" the book manifest itself
        # already recorded as this book's storage_identity.
        if not (book_ctx.cover_subtitle or book_ctx.part or book_ctx.volume) \
        and book_ctx.book_title == "untitled-book" \
        and not book_ctx.book_title_needs_recovery:
            book_ctx.book_folder_name = book_title_override
        # book_title itself is never written from the folder name unless
        # no official title could be parsed at all (no prelims file, or
        # parsing failed -- book_title is still the class default
        # "untitled-book"), since it's the only signal we have then.
        if book_ctx.book_title == "untitled-book":
            book_ctx.book_title = book_title_override

    # subject/klass fallback chain -- prelims parsing (above) is the
    # preferred source, but it silently comes back "unknown" whenever
    # there's no prelims PDF (find_prelims_pdf only recognizes filenames
    # ending in "ps" or containing "prelim") or the prelims page doesn't
    # match parse_book_title_and_class's phrasing. Rather than leave every
    # chapter to re-guess this independently from its own body text (risky
    # -- see auto_detect_subject's docstring), fall back in order to:
    #   1) the book folder name itself (e.g. "Class_12_Chemistry" -- this
    #      is often the most reliable signal we have, since the user named
    #      the folder deliberately) via the same auto_detect_* used for
    #      chapter filenames,
    #   2) each individual chapter filename,
    #   3) the operator-supplied NCERT_DEFAULT_SUBJECT / NCERT_DEFAULT_CLASS
    #      env vars (config.py has always defined these for exactly this
    #      purpose, but nothing previously read them -- this closes that
    #      gap).
    if book_ctx.subject == "unknown" or book_ctx.klass == "unknown":
        fallback_text_sources = []
        if book_title_override:
            fallback_text_sources.append(book_title_override)
        fallback_text_sources.extend(os.path.basename(p) for p in chapter_paths)

        if book_ctx.subject == "unknown":
            for source in fallback_text_sources:
                detected = auto_detect_subject(source, "")
                if detected != "unknown":
                    logger.info("Subject not found in prelims; detected '%s' from '%s'.", detected, source)
                    book_ctx.subject = detected
                    break
            else:
                if DEFAULT_SUBJECT:
                    logger.info("Subject still unknown after detection; using NCERT_DEFAULT_SUBJECT=%s.",
                                DEFAULT_SUBJECT)
                    book_ctx.subject = DEFAULT_SUBJECT

        if book_ctx.klass == "unknown":
            for source in fallback_text_sources:
                detected = auto_detect_class(source, "")
                if detected != "unknown":
                    logger.info("Class not found in prelims; detected '%s' from '%s'.", detected, source)
                    book_ctx.klass = detected
                    break
            else:
                if DEFAULT_CLASS:
                    logger.info("Class still unknown after detection; using NCERT_DEFAULT_CLASS=%s.",
                                DEFAULT_CLASS)
                    book_ctx.klass = DEFAULT_CLASS

    if book_ctx.toc and book_ctx.toc.get("chapters"):
        logger.info("Book '%s' | subject=%s class=%s | %d chapter(s) in TOC",
                     book_ctx.book_title, book_ctx.subject, book_ctx.klass, len(book_ctx.toc["chapters"]))

    if use_vlm:
        logger.info("Pre-loading %s (this happens ONCE for the whole run, reused across every book)...",
                     VLM_MODEL_ID)
        try:
            vlm_inference.get_model()
        except Exception as e:
            logger.error("Could not load VLM (%s). Falling back to deterministic-only extraction "
                         "(semantic fields will be empty). Install torch/transformers/bitsandbytes "
                         "and a GPU, or pass --no-vlm to silence this.", e)
            use_vlm = False

    # Cover-metadata (title + class) VLM recovery fallback -- see
    # modules/pdf_parser.py's needs_vlm_cover_metadata_recovery() /
    # BookContext.book_title_needs_recovery / .klass_needs_recovery
    # docstrings. load_book_context() above stays deterministic-only by
    # design; this is the first point in the run where the VLM is
    # guaranteed loaded, so this is where its fallback belongs.
    #
    # Deliberately keyed off book_title_needs_recovery/klass_needs_recovery
    # (set once, at their true source inside load_book_context()) rather
    # than re-checking `book_ctx.book_title == "untitled-book"` here: the
    # book_title_override folder-name fallback above (line ~2126) may
    # already have overwritten book_title away from that sentinel by this
    # point, which would make such a check always False and silently skip
    # real recovery for the common case where book_orchestrator supplies a
    # folder name for every book. The explicit flags don't have that
    # problem, so a real cover-printed title always still gets a chance to
    # override the folder-name guess here.
    vlm_title_recovered = False
    if use_vlm and prelims_path and pdf_parser.needs_vlm_cover_metadata_recovery(book_ctx):
        try:
            cover_doc = fitz.open(prelims_path)
            result = semantic_processor.process_recover_book_cover_metadata(
                cover_doc, book_ctx.book_title_line_page,
                subject=book_ctx.subject, ocr_title_hint=book_ctx.book_title_ocr_attempt,
            )
            cover_doc.close()
            if book_ctx.book_title_needs_recovery:
                recovered_title = result.get("book_title")
                if recovered_title:
                    logger.info("Recovered book_title via VLM fallback: %r -> %r",
                                book_ctx.book_title_legacy_raw, recovered_title)
                    book_ctx.book_title = recovered_title
                    vlm_title_recovered = True                                     # <-- ADD THIS LINE
                else:
                    logger.warning(
                        "VLM cover recovery did not produce a usable book_title for %s; "
                        "book_title remains %r.", prelims_path, book_ctx.book_title,
                    )
            if book_ctx.klass_needs_recovery and book_ctx.klass == "unknown":
                recovered_klass = str(result.get("klass") or "").strip()
                if recovered_klass.isdigit() and 1 <= int(recovered_klass) <= 12:
                    logger.info("Recovered klass via VLM fallback: %r", recovered_klass)
                    book_ctx.klass = recovered_klass
                else:
                    logger.warning(
                        "VLM cover recovery did not produce a usable klass for %s (got %r); "
                        "klass remains 'unknown'.", prelims_path, recovered_klass,
                    )
        except Exception as e:
            logger.warning("VLM cover-metadata recovery failed for %s (%s); book_title/klass ""remain as previously resolved.", prelims_path, e)

    if book_ctx.book_folder_name is None and book_title_override and not vlm_title_recovered \
        and book_ctx.book_title == "untitled-book" \
        and not (book_ctx.cover_subtitle or book_ctx.part or book_ctx.volume):
        book_ctx.book_folder_name = book_title_override


    total = len(chapter_paths)
    print(f"\nFound {total} PDF{'s' if total != 1 else ''}")
    print("-" * 40)

    written = []
    failed = 0
    cancelled = False
    # Phase F3 (build_executor/): one decision dict per chapter this call
    # actually considered (appended by _f3_execute_chapter() below),
    # feeding this book's own ExecutionPlan once the loop finishes.
    chapter_decisions: List[Dict[str, Any]] = []
    for i, pdf_path in enumerate(chapter_paths, start=1):
        if cancel_check is not None and cancel_check():
            logger.info("Cancellation requested; stopping before chapter %d/%d in '%s'.",
                        i, total, os.path.basename(pdf_folder))
            cancelled = True
            break
        print(f"\nProcessing Chapter {i}/{total}")
        print(os.path.basename(pdf_path))
        try:
            # Derive the real chapter number from the filename itself
            # (NCERT's standard <subject><part><ch-2-digits>.pdf convention)
            # rather than this file's position in *this run's* batch --
            # position is only 1, 2, 3, ... in processing order, which is
            # wrong the moment a run doesn't contain every chapter of the
            # book (e.g. a single newly added chapter dropped in on its
            # own). See chapter_number_from_filename()'s docstring.
            fname_chapter_num = pdf_parser.chapter_number_from_filename(pdf_path)
            chapter_order = fname_chapter_num if fname_chapter_num is not None else i
            if fname_chapter_num is None:
                logger.warning(
                    "Could not parse a chapter number from filename '%s'; falling back to "
                    "this run's processing position (#%d), which is only correct if every "
                    "chapter of the book is present in this run.", os.path.basename(pdf_path), i)
            # Phase F3 (build_executor/) integration point: execute_chapter()
            # IS the pre-execution reuse gate -- it decides reuse/rebuild
            # and only calls process_chapter() (this module's own,
            # unchanged, extraction entry point -- passed in, never
            # imported by build_executor, see executor.py's own DEPENDENCY
            # INJECTION note) when a rebuild is actually required. This
            # does not change what gets written, when a chapter is
            # skipped, or this function's own return shape -- only WHERE
            # that decision is made (before the call, not inside it) and
            # that it is now recorded, per chapter, for Phase F3's own
            # ExecutionPlan/ExecutionReport.
            # Bound via functools.partial rather than adding params to
            # execute_chapter()/build_executor's own signature: process_chapter_fn
            # is called by executor.py with the exact same (pdf_path, book_ctx,
            # chapter_order_fallback=..., use_vlm=..., page_batch_size=...,
            # force=..., output_root=...) call it always has -- these extra
            # kwargs are pre-filled here and never seen by build_executor at
            # all, so Phase F3's own architecture/contract is unchanged.
            process_chapter_bound = functools.partial(
                process_chapter, book_index=book_index, total_books=total_books,
                processing_position=i, total_chapters_in_book=total,
            )
            decision = _f3_execute_chapter(
                pdf_path=pdf_path, book_ctx=book_ctx, chapter_order_fallback=chapter_order,
                use_vlm=use_vlm, page_batch_size=page_batch_size, force=force,
                output_root=output_root, process_chapter_fn=process_chapter_bound,
            )
            chapter_decisions.append(decision)
            out_path = decision["output_path"]
            if out_path:
                written.append(out_path)
                print("✓ Chapter JSON Generated")
            else:
                print("↷ Skipped (already extracted; use --force to redo)")
        except Exception as e:
            # A single bad PDF must never stop the rest of the book.
            failed += 1
            logger.exception("Failed to process '%s': %s", pdf_path, e)
            print(f"✗ Chapter failed: {e}")
        print("-" * 40)

    book_manifest_path = None
    if written and book_ctx.toc:
        book_slug = slugify(pdf_parser.book_slug_source(book_ctx))
        book_manifest_path = json_writer.write_book_manifest(
            book_ctx.klass, book_ctx.subject, book_slug,
            book_ctx.book_title, book_ctx.toc, output_root=output_root,
            cover_subtitle=book_ctx.cover_subtitle, part=book_ctx.part, volume=book_ctx.volume,
            edition=book_ctx.edition, educational_identity=book_ctx.educational_identity,
            storage_identity=book_ctx.derived_storage_identity)

    logger.info("Done. %d chapter JSON file(s) written, %d failed.", len(written), failed)
    stats = {"found": total, "written": len(written), "failed": failed, "book_title": book_ctx.book_title}
    if cancelled:
        # Additive key, only ever present when cancel_check actually fired --
        # existing callers that never pass cancel_check (the fixed default of
        # None) never see this key, so the returned dict shape they rely on
        # is unchanged.
        stats["cancelled"] = True
    # Additive keys (Phase F2, artifact_manager/): the AI_TUTOR-relative
    # paths this call itself just wrote via json_writer, so a caller above
    # pipeline.py (book_orchestrator.run() already returns this dict
    # unchanged; CompilerRuntime/artifact_manager reads it one layer up
    # still) can build a real, comprehensive Build Manifest artifact_
    # locations list without re-deriving any path json_writer already
    # computed. Same "only ever present additively" contract as
    # `cancelled` above -- existing callers that only ever read found/
    # written/failed/book_title are unaffected.
    stats["written_paths"] = list(written)
    stats["book_manifest_path"] = book_manifest_path
    # Phase F3 audit refinement: surface Phase E4's own already-computed
    # `rebuild_order` (incremental_compilation_state's single, chapter-
    # scoped slot -- set by this book's own chapter loop above, right
    # after plan_incremental_compilation() finishes for whichever
    # chapter was last REBUILT this run; still None if every chapter in
    # this book was reused, since a "reuse" decision never calls
    # process_chapter_fn() and therefore never runs Phase E4 at all)
    # into this book's own ExecutionPlan. This reads the exact same
    # already-computed value get_current_incremental_compilation_plan()
    # already exposes -- no new traversal, no re-planning, no second
    # call into incremental_compilation.engine.
    _current_incremental_plan = (
        incremental_compilation_state.get_current_incremental_compilation_plan()
    )
    _dependency_rebuild_order = (
        list(_current_incremental_plan.get("rebuild_order") or [])
        if _current_incremental_plan
        else []
    )
    # Additive keys (Phase F3, build_executor/): this book's own
    # ExecutionPlan, plus the chapter output paths Phase F3 actually
    # reused (never called process_chapter() for) this run -- so a
    # caller above pipeline.py (CompilerRuntime/build_executor reads
    # this one layer up still) can build a run-level ExecutionPlan/
    # ExecutionReport without re-deriving any decision this call
    # already made. Same "only ever present additively" contract as
    # `written_paths`/`book_manifest_path` above -- existing callers
    # that only read found/written/failed/book_title are unaffected.
    stats["execution_plan"] = _f3_generate_execution_plan(
        chapter_decisions, namespace=book_ctx.book_title,
        dependency_rebuild_order=_dependency_rebuild_order,
    )
    stats["reused_paths"] = [
        d["chapter_key"] for d in chapter_decisions if d["decision"] == "reuse"
    ]
    return stats


def main():
    parser = argparse.ArgumentParser(description="NCERT Phase-1 extraction pipeline")
    parser.add_argument("--no-vlm", action="store_true", help="Skip Qwen2.5-VL calls (deterministic-only dry run)")
    parser.add_argument("--force", action="store_true", help="Re-extract even if chapter JSON already exists")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_PAGE_BATCH_SIZE, help="Pages per VLM batch (4-8)")
    args = parser.parse_args()

    # Orchestration/input-discovery layer: decides whether pdf_in/ holds one
    # book (old flat layout) or many book subfolders, then calls
    # process_all_pdfs() above once per book. See book_orchestrator.py --
    # nothing about *how* a single book is processed changes here, only
    # *how many times, and over which folder,* process_all_pdfs() is called.
    import book_orchestrator
    book_orchestrator.run(use_vlm=not args.no_vlm, page_batch_size=args.batch_size, force=args.force)


if __name__ == "__main__":
    main()