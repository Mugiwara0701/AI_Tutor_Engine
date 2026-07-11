"""
dependency_graph/ — Phase E2: Build Dependency Graph.

SCOPE: this package models COMPILATION dependencies only -- which
compiler artifact was built from which other already-built compiler
artifact, for one chapter's compilation run. It is NOT the Knowledge
Graph (knowledge_graph/), carries no educational relationship of any
kind (no "explains", "prerequisite", "related_to", ...), and never
reads or references chapter content (topics, concepts, definitions,
...) directly. Where the Knowledge Graph answers "what does this
chapter teach and how do those ideas relate", the Build Dependency
Graph answers only "what build step produced this artifact, and what
did that step itself require to already exist" -- a build-system DAG
over Phase B/C/D/E1's own already-computed outputs, nothing more.

  * `identity.py` -- deterministic id/urn builders for this graph's own
    graph/node/edge identities, the exact same "pure string-builder,
    reused as-is" shape as knowledge_graph/identity.py, given its own
    urn namespace segment (`dg`) so a Dependency Graph urn can never
    collide with a Knowledge Graph urn or a Compiler IR urn even
    though all three share the same urn root.
  * `node.py` -- `DependencyNode`: one node per compiler artifact this
    chapter actually produced (a compiler registry, a Knowledge Graph
    registry, a manifest, a statistics report, a fingerprint set, a
    readiness report, a build summary, or Build Metadata itself).
  * `edge.py` -- `DependencyEdge`: one directed `depends_on` edge per
    "this artifact could not have been built without that artifact
    already existing" relationship between two DependencyNodes.
  * `exceptions.py` -- this package's own exception hierarchy, mirrors
    knowledge_graph/exceptions.py's shape and role one package over.
  * `registries.py` -- `DependencyRegistryManager`, a thin subclass of
    compiler.registry_manager.RegistryManager (reused directly, not
    reimplemented), owning two registries: `nodes` and `edges`. Exact
    same relationship knowledge_graph/registries.py's
    `GraphRegistryManager` already has to the same base class.
  * `schema.py` -- `DependencyGraphMetadata` + `DependencyGraph`, the
    graph-level container this package ultimately produces.
  * `build.py` -- `generate_dependency_graph()`, the one read-only pass
    that constructs this chapter's DependencyGraph from Phase
    B-D3/E1's already-computed artifacts. Never inserts into, updates,
    or removes from any Compiler IR or Knowledge Graph registry; never
    mutates any manifest/statistics/fingerprint/readiness-report/
    build-summary/BuildMetadata dict it reads.
  * `state.py` -- the module-level "current chapter's DependencyGraph"
    slot, following the exact single-slot idiom build_metadata/state.py
    already establishes one phase down (see that module's own
    docstring) -- nothing here needs per-sub-artifact slots, since
    (exactly as with BuildMetadata) nothing downstream ever consumes
    less than the whole assembled graph.

WHAT THIS IS NOT (see task's own DO NOT IMPLEMENT list): this is not
Change Detection (E3), not Incremental Compilation (E4), not
Validation & Finalization (E5), not a Persistence Store, not an
Incremental Planner, not Dirty Object Detection, not a Minimal Rebuild
Planner, not a Build Cache, and not Dependency Validation. Phase E2
only builds and stores the dependency graph itself -- it never reads
it back to decide what to rebuild, never persists it to disk, and
never validates its own shape (a self-consistency check would be a
dependency-validation concern, explicitly out of scope here).
"""