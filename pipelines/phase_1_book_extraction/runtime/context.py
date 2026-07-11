"""
runtime/context.py — Phase F1: RuntimeStatus lifecycle constants and the
ExecutionContext dataclass.

Execution context, in F0 §3/§8's sense, is simply "the configuration one
run() call executes with" -- the same use_vlm / page_batch_size / force /
pdf_input_folder knobs book_orchestrator.run() and pipeline.process_all_pdfs()
already accept as plain keyword arguments, now captured as a single
immutable snapshot so runtime.state.py (and status()) can report exactly
what a run was/is executing with, without re-deriving it from
CompilerRuntime's own __init__ arguments each time.

RuntimeStatus is a small closed set of string constants, not an enum.Enum,
to match this codebase's own established convention for "verdict" values
that live in state.py (final_status strings like "READY" /
"READY_WITH_WARNINGS" / "FAILED" already used by compiler/state.py and
incremental_compilation_finalization/state.py are plain strings, not
Enums) -- staying consistent with what's already here rather than
introducing a new style for Phase F1 alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class RuntimeStatus:
    """Closed set of CompilerRuntime lifecycle states (F0 §8's Runtime
    Lifecycle diagram, narrowed to what Phase F1 alone owns -- no
    Input-Manifest/build-strategy/packaging states here, those belong to
    F2-F5).

        IDLE somebody constructed a CompilerRuntime; run() has never been
             called (or shutdown() reset nothing to report -- IDLE is
             also, deliberately, the default status() would show for a
             freshly-shut-down instance's underlying build state, though
             SHUT_DOWN below is what's actually reported once shutdown()
             has run).
        RUNNING          run()/resume() is currently executing.
        CANCEL_REQUESTED cancel() was called while RUNNING; the
                         cooperative cancel_check hook (see pipeline.
                         process_all_pdfs()'s own cancel_check parameter)
                         will be honored at the next chapter/book
                         boundary.
        CANCELLED        the run stopped early because cancel() was
                         honored.
        COMPLETED        run()/resume() finished without cancellation or
                         an unhandled error.
        FAILED           run()/resume() raised -- see state.py's
                         last_error for what.
        SHUT_DOWN        shutdown() has been called; this instance will
                         never run() again.
    """
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SHUT_DOWN = "SHUT_DOWN"


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable snapshot of the configuration one run()/resume() call
    executes with -- exactly the arguments book_orchestrator.run() and
    pipeline.process_all_pdfs() already accept (reused, not duplicated;
    Phase F1 introduces no new configuration knobs of its own, see F0 §4
    "Phase F NEVER owns ... extraction_config_values" — those remain
    Stage A-E's/config.py's)."""
    use_vlm: bool
    page_batch_size: int
    force: bool
    pdf_input_folder: Optional[str] = None