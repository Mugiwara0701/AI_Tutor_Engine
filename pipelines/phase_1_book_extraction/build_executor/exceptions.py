"""
build_executor/exceptions.py — Phase F3: exception hierarchy for the
Build Executor (build_executor.executor/plan/report/state).

Mirrors artifact_manager/exceptions.py's own convention exactly, one
package over: small, specific exception classes so a caller can catch
precisely what it cares about instead of parsing free-text messages.

These are Phase F3's OWN exceptions -- they describe build-executor-
level failures (an ExecutionPlan that fails its own invariants, an
ExecutionReport that can't be generated deterministically), not
compiler/knowledge-graph/incremental-compilation errors. An error
raised by an orchestrated phase is never wrapped or hidden by these
classes; it already propagated through pipeline.process_chapter()/
CompilerRuntime.run() before Phase F3's own integration points ever
run (see executor.py's own "never raises" contract at the
CompilerRuntime integration point, mirroring artifact_manager's own
_record_build() contract one phase up).
"""


class BuildExecutorError(Exception):
    """Base class for every error raised anywhere in the
    build_executor package. Mirrors artifact_manager.exceptions.
    ArtifactManagerError's role as the one catch-all ancestor for its
    own layer."""


class ExecutionPlanError(BuildExecutorError):
    """Raised when an ExecutionPlan cannot be generated deterministically
    from the chapter decisions/artifacts it was given -- e.g. a required
    field is missing so no plan could possibly reference it."""


class ExecutionReportError(BuildExecutorError):
    """Raised when an ExecutionReport cannot be generated from an
    already-constructed ExecutionPlan -- e.g. the plan itself is
    missing or malformed."""