"""
incremental_compilation_finalization/exceptions.py — Phase E5.2:
exception hierarchy for the Incremental Compilation Finalization layer.

Mirrors incremental_compilation_validation/exceptions.py's own
convention exactly, one package over: small, specific exception
classes so a caller can catch precisely what it cares about instead of
parsing free-text messages.
"""


class IncrementalCompilationFinalizationError(Exception):
    """Base class for every error raised anywhere in the
    incremental_compilation_finalization package. Mirrors
    incremental_compilation_validation.exceptions.
    IncrementalCompilationValidationError's role as the one catch-all
    ancestor for its own layer."""
