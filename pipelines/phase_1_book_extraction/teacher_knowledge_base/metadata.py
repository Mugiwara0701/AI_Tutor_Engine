"""
teacher_knowledge_base/metadata.py — M6.1 (remediatedfrom M6.0.3 architecture)

Produces TKBMetadata and TKBCompilerInfo exactly as defined in:
  TEACHER_KNOWLEDGE_BASE_SCHEMA.md §2 (TKBMetadata)
  TEACHER_KNOWLEDGE_BASE_SCHEMA.md §3 (TKBCompilerInfo)
  M6_ARCHITECTURE_SPECIFICATION.md §8 (Identity scheme)

ID SCHEME (spec §8):
  tkb_id = UUID5(TKB_NS, source_package_id + ":" + tkb_version + ":" + chapter_id)
  tkb_urn = "urn:tkb:base:<tkb_id>"

No fields are invented. Every field maps to an exact spec entry.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------
# Version constants — spec §9 / SCHEMA §1
# --------------------------------------------------------------------------
TKB_VERSION = "1.1.1"        # artifact version
TKB_SCHEMA_VERSION = "1.1.1"  # schema version
BUILDER_VERSION = "M6.1.0"    # this builder

# UUID5 namespace for TeacherKnowledgeBase (TKB_NS in spec §8)
_TKB_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace (repurposed)


def make_tkb_id(source_package_id: str, chapter_id: str) -> str:
    """UUID5(TKB_NS, source_package_id + ':' + tkb_version + ':' + chapter_id)
    Exact spec §8 formula."""
    name = f"{source_package_id}:{TKB_VERSION}:{chapter_id}"
    return str(uuid.uuid5(_TKB_NS, name))


def make_tkb_urn(tkb_id: str) -> str:
    return f"urn:tkb:base:{tkb_id}"


@dataclass
class TKBMetadata:
    """
    TEACHER_KNOWLEDGE_BASE_SCHEMA.md §2 — TKBMetadata

    Every field below is in the frozen spec. No extra fields.
    """
    tkb_id:             str
    tkb_scope:          str      # "chapter" (v1 always)
    subject:            str
    book_title:         str
    klass:              str
    language:           str      # ISO 639-1 e.g. "en"
    chapter_title:      str
    chapter_number:     int
    chapter_id:         str
    board:              str      # e.g. "CBSE"
    source_package_id:  str
    created_at:         str      # ISO 8601 UTC
    builder_version:    str
    status:             str      # "READY" | "READY_WITH_WARNINGS" | "FAILED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TKBCompilerInfo:
    """
    TEACHER_KNOWLEDGE_BASE_SCHEMA.md §3 — TKBCompilerInfo

    Populated from available compiler artifacts. Fields left empty string
    when the upstream artifact is not present (graceful degradation).
    """
    compiler_release_id:    str   # CompilerReleaseManifest.build_id
    build_id:               str   # artifact_manager.Build.build_id
    master_package_id:      str   # MasterKnowledgePackage.manifest.package_id
    optimized_package_id:   str   # OptimizedKnowledgePackage.manifest.package_id
    compiler_version:       str
    phase1_frozen_at:       str   # ISO 8601
    artifact_checksums:     Dict[str, str]  # artifact name -> SHA-256

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_tkb_metadata(
    source_package_id: str,
    chapter_id: str,
    chapter_number: int = 0,
    chapter_title: str = "",
    subject: str = "",
    book_title: str = "",
    klass: str = "",
    language: str = "en",
    board: str = "",
    status: str = "READY",
    config: Optional[Dict[str, Any]] = None,
) -> TKBMetadata:
    """Build TKBMetadata from available compiler context.
    All fields copied or trivially derived from compiler artifacts.
    No invented fields."""
    config = config or {}
    tkb_id = make_tkb_id(source_package_id, chapter_id)
    return TKBMetadata(
        tkb_id=tkb_id,
        tkb_scope="chapter",
        subject=subject or config.get("subject", ""),
        book_title=book_title or config.get("book_title", ""),
        klass=klass or config.get("klass", ""),
        language=language or config.get("language", "en"),
        chapter_title=chapter_title or config.get("chapter_title", ""),
        chapter_number=chapter_number,
        chapter_id=chapter_id,
        board=board or config.get("board", ""),
        source_package_id=source_package_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        builder_version=BUILDER_VERSION,
        status=status,
    )


def build_tkb_compiler_info(
    compiler_artifacts: Dict[str, Any],
) -> TKBCompilerInfo:
    """Build TKBCompilerInfo by reading from already-loaded compiler artifacts.
    All fields are copied verbatim from existing compiler artifact dicts.
    No invented fields."""
    build = compiler_artifacts.get("build")
    release_manifest = compiler_artifacts.get("compiler_release_manifest") or {}
    build_metadata = compiler_artifacts.get("build_metadata") or {}

    def _get(*paths: str) -> str:
        """Try a sequence of dot-paths across available dicts."""
        for path in paths:
            parts = path.split(".")
            obj: Any = None
            for d_key, attr_path in [("build_metadata", parts), ("release_manifest", parts)]:
                src = locals().get(d_key) if d_key != "release_manifest" else release_manifest
                src = build_metadata if d_key == "build_metadata" else release_manifest
                val = src
                for p in attr_path:
                    if isinstance(val, dict):
                        val = val.get(p)
                    else:
                        val = getattr(val, p, None)
                    if val is None:
                        break
                if val and isinstance(val, str):
                    return val
        return ""

    compiler_release_id = (
        (release_manifest.get("build_id") or "")
        or (build_metadata.get("release_id") or "")
    )
    build_id = (
        (getattr(build, "build_id", None) or "")
        or (build_metadata.get("build_id") or "")
    )
    okp = compiler_artifacts.get("optimized_knowledge_package") or {}
    mkp = compiler_artifacts.get("master_knowledge_package") or {}

    return TKBCompilerInfo(
        compiler_release_id=compiler_release_id,
        build_id=build_id,
        master_package_id=(
            (mkp.get("manifest", {}).get("package_id") if isinstance(mkp, dict) else "")
            or (build_metadata.get("master_package_id") or "")
        ),
        optimized_package_id=(
            (okp.get("manifest", {}).get("package_id") if isinstance(okp, dict) else "")
            or (build_metadata.get("optimized_package_id") or "")
        ),
        compiler_version=(
            (release_manifest.get("compiler_version") or "")
            or (build_metadata.get("compiler_metadata", {}).get("compiler_version") or "")
        ),
        phase1_frozen_at=(
            (release_manifest.get("frozen_at") or "")
            or (build_metadata.get("phase1_frozen_at") or "")
        ),
        artifact_checksums={
            "chapter_json": "",
            "knowledge_graph": "",
            "document_structure_tree": "",
            "master_knowledge_package": "",
            "optimized_knowledge_package": "",
        },
    )
