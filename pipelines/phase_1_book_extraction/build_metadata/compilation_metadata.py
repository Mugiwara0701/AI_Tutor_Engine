"""
build_metadata/compilation_metadata.py — Phase E1: CompilationMetadata.

CompilationMetadata is the OPERATIONAL half of BuildMetadata: which PDF
was compiled, when, with what CLI/batch configuration, and how long it
took. Every field here is either read directly from process_chapter()'s
own already-in-scope arguments/locals (pdf_path, use_vlm,
page_batch_size, force, the chapter's own start/end wall-clock times) or
is a cheap, local, one-time computation (the source PDF's content hash)
-- nothing here re-runs any extraction, parsing, or compilation step.

NEVER PARTICIPATES IN ANY FINGERPRINT: compilation_start/compilation_end/
processing_time_seconds are wall-clock timestamps and durations -- exactly
the kind of run-to-run-varying field canonicalization.py's own
VOLATILE_KEYS excludes from every fingerprint in this codebase (see e.g.
"generated_at"). CompilationMetadata is deliberately never passed into
configuration_metadata.py's fingerprint computation, and BuildMetadata
never derives a fingerprint of its own that includes it.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# This module's own version marker -- independent of every other *_VERSION
# constant in this codebase, following the same per-module convention
# (see e.g. compiler/finalize.py's own FINALIZE_VERSION). Bump only if the
# SHAPE this module produces changes in a way a consumer should be able
# to detect.
COMPILATION_METADATA_VERSION = "E1.1"


def _source_pdf_content_hash(pdf_path: Optional[str]) -> Optional[str]:
    """SHA-256 hex digest of the source PDF's raw bytes, or None if
    `pdf_path` is falsy or the file cannot be read (e.g. already deleted
    by the time BuildMetadata is generated) -- this is operational,
    best-effort provenance, not a correctness gate, so a read failure
    here must never fail chapter compilation. Reads the file directly
    (unlike canonicalization.py's canonical_json()/sha256_hexdigest(),
    which hash canonical JSON *text* of already-computed dicts) since
    the input here is raw PDF bytes, not a dict this codebase has any
    existing canonicalization strategy for."""
    if not pdf_path:
        return None
    try:
        digest = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


@dataclass
class CompilationMetadata:
    """The full Phase E1 CompilationMetadata artifact. Purely a data
    holder; all aggregation happens in generate_compilation_metadata()
    below."""

    generated_at: str
    compilation_metadata_version: str
    source_pdf: Optional[str]
    source_pdf_content_hash: Optional[str]
    compilation_start: Optional[str]
    compilation_end: Optional[str]
    processing_time_seconds: Optional[float]
    cli_invocation: Dict[str, Any]
    batch_configuration: Dict[str, Any]
    compiler_execution_info: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_compilation_metadata(
    *,
    pdf_path: Optional[str],
    compilation_start: Optional[datetime] = None,
    compilation_end: Optional[datetime] = None,
    processing_time_seconds: Optional[float] = None,
    use_vlm: bool = True,
    page_batch_size: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Phase E1: builds this chapter's CompilationMetadata. `pdf_path`,
    `use_vlm`, `page_batch_size`, and `force` are process_chapter()'s own
    already-in-scope arguments, threaded through unchanged (same "reuse,
    don't recompute" rule every earlier phase's own aggregation pass
    follows). `compilation_start`/`compilation_end` are wall-clock
    datetimes the caller captured around this chapter's compilation (see
    pipeline.py's own integration point); `processing_time_seconds`, if
    not supplied, falls back to the difference between them.

    Read-only: never touches the Compiler IR, the Knowledge Graph, or
    Chapter JSON, and performs no extraction/parsing of its own beyond
    hashing the source PDF's bytes."""
    if processing_time_seconds is None and compilation_start and compilation_end:
        processing_time_seconds = round(
            (compilation_end - compilation_start).total_seconds(), 2
        )

    metadata = CompilationMetadata(
        generated_at=datetime.now(timezone.utc).isoformat(),
        compilation_metadata_version=COMPILATION_METADATA_VERSION,
        source_pdf=os.path.basename(pdf_path) if pdf_path else None,
        source_pdf_content_hash=_source_pdf_content_hash(pdf_path),
        compilation_start=compilation_start.isoformat() if compilation_start else None,
        compilation_end=compilation_end.isoformat() if compilation_end else None,
        processing_time_seconds=processing_time_seconds,
        cli_invocation={
            "use_vlm": use_vlm,
            "page_batch_size": page_batch_size,
            "force": force,
        },
        batch_configuration={
            "page_batch_size": page_batch_size,
        },
        compiler_execution_info={
            "pdf_path": pdf_path,
        },
    )
    return metadata.to_dict()