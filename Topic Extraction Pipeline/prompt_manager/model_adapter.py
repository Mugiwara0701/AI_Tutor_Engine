"""
model_adapter.py — the abstract interface prompt_manager depends on.

prompt_manager never imports a concrete model. It only ever holds a
ModelAdapter instance and calls .generate_json(). This is what makes swapping
or adding a backend later (InternVL, MiniCPM, ...) a matter of writing a new
adapter class, not touching prompt_manager's internals.

Scope note: only ONE concrete adapter (Qwen) is being implemented
(adapters/qwen_adapter.py). This file is interface-only.

--- Interface change vs the initial version (flagged per your clarification) ---
Originally this interface only had `generate()` returning raw text, and
prompt_manager did its own defensive JSON parsing. Per clarification #2,
all model-specific response cleanup (markdown-fence stripping, minor JSON
repair, parsing) now belongs to the adapter, not prompt_manager — different
backends may need different cleanup quirks handled differently. That
requires the adapter to hand back a *parsed* result, not just raw text, so
`generate_json()` is added as a second abstract method returning the
structured `AdapterResponse` below. `generate()` is kept as-is (some future
caller may still want raw text only); `generate_json()` is what
prompt_manager actually calls.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


@dataclass
class AdapterResponse:
    """What every concrete adapter's generate_json() returns. Shape is
    adapter-agnostic so prompt_manager can treat any adapter identically."""
    success: bool
    raw_output: str                       # exactly what the model returned, untouched
    cleaned_output: str                   # after adapter-specific cleanup (fence stripping etc.)
    parsed_output: Optional[Dict[str, Any]]  # None if parsing failed
    error_message: Optional[str] = None   # set when success is False


class ModelAdapter(ABC):
    """Every concrete adapter (qwen_adapter, and any future one) must
    implement this. prompt_manager calls nothing else on an adapter."""

    #: short stable identifier logged into TaskResult.model_adapter_id
    #: (e.g. "qwen2.5-vl-3b-instruct"). Concrete adapters must set this.
    adapter_id: str = "unset-adapter"

    @abstractmethod
    def generate(self, prompt: str, images: Optional[List[Any]] = None,
                 max_new_tokens: Optional[int] = None) -> str:
        """Runs one inference call and returns the model's raw text output,
        completely unprocessed. `images` is a list of PIL.Image (or
        empty/None for text-only tasks). Must raise on unrecoverable failure.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_json(self, prompt: str, images: Optional[List[Any]] = None,
                       max_new_tokens: Optional[int] = None) -> AdapterResponse:
        """Runs one inference call AND handles all model-specific response
        cleanup + JSON parsing, returning a structured AdapterResponse.
        Must NOT raise for "the model didn't return valid JSON" — that's an
        expected, ordinary outcome and must come back as
        AdapterResponse(success=False, error_message=...), not an exception.
        prompt_manager treats an exception here as an infrastructure failure
        (e.g. GPU OOM), not a validation-retry case.
        """
        raise NotImplementedError

    def token_counts(self) -> Optional[dict]:
        """Optional. Adapters that can surface prompt/completion token counts
        from their last call should override this; prompt_manager treats a
        None return as 'not available' rather than an error."""
        return None
