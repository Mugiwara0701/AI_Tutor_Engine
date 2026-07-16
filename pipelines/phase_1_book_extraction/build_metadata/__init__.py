"""
build_metadata/ -- Phase E1: BuildMetadata (the top-level aggregation
artifact), plus its Milestone 5.2 DST-integration additions.

Package exports: the imports/`__all__` below re-export every public
symbol from build_metadata/build.py -- the single source of truth for
this package's dataclasses and generate_*/attach_*/finalize_* functions
-- so `from build_metadata import <anything public>` works uniformly,
exactly like compiler/__init__.py, knowledge_graph/__init__.py,
dependency_graph/__init__.py, and artifact_manager/__init__.py already
do for their own `.build` module. See build_metadata/build.py's own
module docstring for the actual SCOPE/REUSE-DON'T-RECOMPUTE writeup;
nothing is reimplemented here.
"""
from .build import (
    BUILD_METADATA_VERSION,
    CompilerMetadata,
    generate_compiler_metadata,
    GraphMetadata,
    generate_graph_metadata,
    DSTMetadata,
    generate_dst_metadata,
    BuildMetadata,
    generate_build_metadata,
    finalize_build_metadata,
    attach_dst_metadata,
)

__all__ = [
    "BUILD_METADATA_VERSION",
    "CompilerMetadata",
    "generate_compiler_metadata",
    "GraphMetadata",
    "generate_graph_metadata",
    "DSTMetadata",
    "generate_dst_metadata",
    "BuildMetadata",
    "generate_build_metadata",
    "finalize_build_metadata",
    "attach_dst_metadata",
]