"""
runtime/exceptions.py — Phase F1: exception hierarchy for the Compiler
Runtime (runtime/runtime.py's CompilerRuntime).

Mirrors compiler/exceptions.py's and change_detection/exceptions.py's own
convention exactly, one layer up: small, specific exception classes so a
caller can catch precisely what it cares about (e.g. catch
RuntimeAlreadyRunningError to report "a run is already in progress"
without parsing free-text messages) instead of a bare Exception.

These are Phase F1's OWN exceptions -- they describe runtime lifecycle
misuse (calling run() twice concurrently, calling anything after
shutdown(), etc.), not compiler/knowledge-graph/etc. errors. An error
raised by one of the orchestrated phases (RegistryError,
ChangeDetectionError, ...) is never wrapped or hidden by these classes --
see runtime/runtime.py's CompilerRuntime.run() docstring for exactly how
such an error propagates through the runtime unchanged (Phase F1's
"error propagation" requirement).
"""


class CompilerRuntimeError(Exception):
    """Base class for every error raised by runtime.runtime.CompilerRuntime
    itself, describing lifecycle misuse rather than a failure inside an
    orchestrated phase (compiler, knowledge_graph, ... errors propagate
    through CompilerRuntime unchanged and are never instances of this
    class -- see module docstring)."""


class RuntimeAlreadyRunningError(CompilerRuntimeError):
    """Raised by run()/resume() when this CompilerRuntime's status is
    already RUNNING. One CompilerRuntime instance runs one build at a
    time -- same single-chapter-at-a-time, not-concurrency-safe design
    already established by every *_state.py module this runtime's own
    state.py mirrors (see runtime/state.py's module docstring)."""

    def __init__(self, status: str):
        super().__init__(
            f"runtime: run()/resume() called while status is already "
            f"{status!r} -- one CompilerRuntime instance runs one build "
            "at a time. Use status() to check before calling run() again, "
            "or cancel() to request the in-progress run stop."
        )
        self.status = status


class RuntimeShutDownError(CompilerRuntimeError):
    """Raised by run()/resume()/cancel() once shutdown() has been called
    on this CompilerRuntime instance. A shut-down runtime is permanently
    inert -- construct a new CompilerRuntime for a new build."""

    def __init__(self):
        super().__init__(
            "runtime: this CompilerRuntime has already been shut down and "
            "cannot start, resume, or cancel a build. Construct a new "
            "CompilerRuntime instance for a new build."
        )


class RuntimeNotRunningError(CompilerRuntimeError):
    """Raised by resume() when there is no prior run to resume from --
    i.e. status() has never left IDLE. resume() re-invokes the same
    orchestration run() does, relying on pipeline.py's own existing
    is_already_extracted()/force=False resumability (see runtime/
    runtime.py's resume() docstring); calling it with nothing to resume
    is almost always a caller mistake, so this raises rather than
    silently behaving like a fresh run()."""

    def __init__(self, status: str):
        super().__init__(
            f"runtime: resume() called but status is {status!r} -- there "
            "is no previous run to resume. Call run() to start a new "
            "build."
        )
        self.status = status