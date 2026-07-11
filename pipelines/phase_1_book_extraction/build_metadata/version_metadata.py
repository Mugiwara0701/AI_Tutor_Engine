"""
build_metadata/version_metadata.py — Phase E1: VersionMetadata.

VersionMetadata AGGREGATES version markers Phases B-D3 already declared
-- it never redeclares, duplicates, or modifies a single one of them.
Every constant imported below is imported FROM the module that already
owns it (exactly compiler/build.py's own `registry_versions` /
knowledge_graph/build.py's own `node_registry_versions` convention of
importing each pass's *_VERSION constant from its owning module, reused
here one layer up): compiler_version/schema_version/build_version come
from the already-computed Compiler Manifest, graph_schema_version/
identity_version from the already-computed Knowledge Graph Manifest, and
the remaining phase_versions are each phase's own already-declared
FINALIZE_VERSION/SYSTEM_INTEGRITY_VERSION/DETERMINISM_VERSION/
RELEASE_VERSION constant.

This codebase has no single unified "pipeline version" constant (unlike
COMPILER_VERSION, which versions Phase B specifically) -- so, per the
same REUSE, DON'T RECOMPUTE rule every earlier phase in this codebase
already follows (never invent a new version field that duplicates or
supersedes an existing one), VersionMetadata surfaces the actual
per-phase version markers under
`phase_versions` instead of fabricating a composite "pipeline_version"
no other module defines.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from compiler.finalize import FINALIZE_VERSION as COMPILER_FINALIZE_VERSION
from knowledge_graph.finalize import GRAPH_FINALIZE_VERSION
from validation.system_integrity import SYSTEM_INTEGRITY_VERSION
from validation.determinism import DETERMINISM_VERSION
from validation.release import RELEASE_VERSION

# This module's own version marker -- independent of every other *_VERSION
# constant in this codebase (see e.g. compiler/finalize.py's own
# FINALIZE_VERSION). Bump only if the SHAPE this module produces changes
# in a way a consumer should be able to detect.
VERSION_METADATA_VERSION = "E1.1"


@dataclass
class VersionMetadata:
    """The full Phase E1 VersionMetadata artifact. Purely a data holder;
    all aggregation happens in generate_version_metadata() below."""

    generated_at: str
    version_metadata_version: str
    compiler_version: Optional[str]
    schema_version: Optional[str]
    build_version: Optional[str]
    graph_schema_version: Optional[str]
    identity_version: Optional[str]
    phase_versions: Dict[str, str]
    phase_completion: Dict[str, Optional[str]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_version_metadata(
    *,
    compiler_manifest: Optional[Dict[str, Any]],
    knowledge_graph_manifest: Optional[Dict[str, Any]],
    final_compiler_status: Optional[str],
    final_graph_status: Optional[str],
    release_status: Optional[str],
) -> Dict[str, Any]:
    """Phase E1: builds this chapter's VersionMetadata. Every version
    field is read from an already-computed manifest (`compiler_manifest`
    -- Phase B5.1, `knowledge_graph_manifest` -- Phase C4.1) or imported
    directly from the module that already declares it (Phase B5.3/C4.3/
    D1/D2/D3's own FINALIZE_VERSION/GRAPH_FINALIZE_VERSION/
    SYSTEM_INTEGRITY_VERSION/DETERMINISM_VERSION/RELEASE_VERSION) --
    nothing here re-derives a version marker any earlier phase already
    owns.

    `final_compiler_status`/`final_graph_status`/`release_status` are
    each already-computed Phase B5.3/C4.3/D3 verdicts, folded into
    `phase_completion` under this artifact's own field name -- never a
    fourth, independently computed judgment.

    Read-only over every argument."""
    compiler_manifest = compiler_manifest or {}
    knowledge_graph_manifest = knowledge_graph_manifest or {}

    phase_versions = {
        "compiler_finalize": COMPILER_FINALIZE_VERSION,
        "graph_finalize": GRAPH_FINALIZE_VERSION,
        "system_integrity": SYSTEM_INTEGRITY_VERSION,
        "determinism": DETERMINISM_VERSION,
        "release": RELEASE_VERSION,
    }
    phase_completion = {
        "compiler": final_compiler_status,
        "knowledge_graph": final_graph_status,
        "release": release_status,
    }

    metadata = VersionMetadata(
        generated_at=datetime.now(timezone.utc).isoformat(),
        version_metadata_version=VERSION_METADATA_VERSION,
        compiler_version=compiler_manifest.get("compiler_version"),
        schema_version=compiler_manifest.get("schema_version"),
        build_version=compiler_manifest.get("build_version"),
        graph_schema_version=knowledge_graph_manifest.get("graph_schema_version"),
        identity_version=knowledge_graph_manifest.get("identity_version"),
        phase_versions=phase_versions,
        phase_completion=phase_completion,
    )
    return metadata.to_dict()