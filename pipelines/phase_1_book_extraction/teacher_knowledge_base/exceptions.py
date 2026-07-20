"""
teacher_knowledge_base/exceptions.py — M6.1: Exception hierarchy for the
Teacher Knowledge Base package.

Mirrors artifact_manager/exceptions.py's and build_executor/exceptions.py's
own convention exactly, one package over: small, specific exception classes
so a caller can catch precisely what it cares about instead of parsing
free-text messages.

These are M6.1's OWN exceptions — they describe TKB-level failures
(a builder stage that cannot complete, a validation violation, a
serialization failure, an artifact that cannot be registered), not
compiler/knowledge-graph/... errors. An error raised by an orchestrated
phase (ArtifactManagerError, BuildError, ...) is never wrapped or hidden
by these classes; it already propagated through the upstream pipeline
before M6.1's own integration point ever runs.
"""


class TeacherKnowledgeBaseError(Exception):
    """Base class for every error raised anywhere in the
    teacher_knowledge_base package. Mirrors ArtifactManagerError's role
    as the one catch-all ancestor for its own layer."""


class TKBBuildError(TeacherKnowledgeBaseError):
    """Raised when the TKB build pipeline cannot complete — e.g. a required
    compiler artifact is missing, a builder stage fails, or pipeline
    context is malformed. Never raised for a validation finding (that is
    TKBValidationError) — only for M6.1's own inability to execute a build
    stage."""


class TKBValidationError(TeacherKnowledgeBaseError):
    """Raised when TKB validation discovers a violation that prevents a
    valid artifact from being produced — schema violations, ownership
    conflicts, broken graph edges, duplicate IDs, reference failures."""

    def __init__(self, violation: str, detail: str = ""):
        msg = f"TKB validation: {violation}"
        if detail:
            msg = f"{msg} — {detail}"
        super().__init__(msg)
        self.violation = violation
        self.detail = detail


class TKBSerializationError(TeacherKnowledgeBaseError):
    """Raised when deterministic serialization of the TKB artifact fails —
    e.g. an object cannot be reduced to a JSON-safe dict, or stable
    ordering cannot be achieved."""


class TKBRegistrationError(TeacherKnowledgeBaseError):
    """Raised when the TKB artifact cannot be registered with the Artifact
    Manager or the Registry Framework — e.g. a required build context is
    absent."""


class TKBLoaderError(TeacherKnowledgeBaseError):
    """Raised when a required compiler artifact (OptimizedKnowledgePackage,
    MasterKnowledgePackage, KnowledgeGraph, DocumentStructureTree,
    SemanticGraph, ChapterJSON, CompilerReleaseManifest) cannot be
    located or loaded from the available build state."""

    def __init__(self, artifact_name: str, detail: str = "not found"):
        super().__init__(
            f"teacher_knowledge_base loader: {artifact_name!r} — {detail}"
        )
        self.artifact_name = artifact_name


class TKBBuilderError(TeacherKnowledgeBaseError):
    """Raised by an individual sub-builder (EDSTBuilder, EKGBuilder,
    EDGBuilder, TeachingUnitBuilder, etc.) when it cannot produce its
    output — e.g. missing source data, broken references, or an
    invariant violation specific to that builder stage."""

    def __init__(self, stage: str, detail: str = ""):
        msg = f"TKB builder [{stage}]: failed"
        if detail:
            msg = f"{msg} — {detail}"
        super().__init__(msg)
        self.stage = stage


class TKBAmbiguityError(TeacherKnowledgeBaseError):
    """Raised (or recorded as a documented ambiguity) when implementation
    reveals an architectural ambiguity in the frozen specifications.
    Per M6.1 rules: STOP, document it, do NOT silently redesign."""

    def __init__(self, spec_reference: str, description: str):
        super().__init__(
            f"TKB architectural ambiguity in {spec_reference!r}: {description}. "
            f"Implementation halted. Resolve in architecture before proceeding."
        )
        self.spec_reference = spec_reference
        self.description = description
