"""
prompt_manager.py — the single facade every extraction module calls for any
VLM interaction. Owns task routing, context assembly, output validation.
Model abstraction lives behind model_adapter.ModelAdapter; this module never
imports a concrete model, and (per clarification #2) never does any
model-specific response cleanup or JSON parsing itself — that is entirely
the adapter's responsibility via generate_json(). prompt_manager's job is
strictly: build prompt, call adapter, validate against the output contract,
return TaskResult.

    result = prompt_manager.run(task_name, context, model_override=None)

Dependency direction (per frozen design): prompt_manager depends only on its
own submodules (task_registry, context_builder, output_contract) and an
injected ModelAdapter. It never imports or reaches into any extraction
module, and never fetches pipeline state itself — context flows in as data
from the caller.
"""
import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from prompt_manager import task_registry, context_builder, output_contract
from prompt_manager.model_adapter import ModelAdapter

logger = logging.getLogger("ncert_pipeline.prompt_manager")


class MissingContextError(Exception):
    """Raised when a caller's TaskContext doesn't supply everything the
    task's current template version declares it needs. Raised BEFORE any
    model call — a malformed prompt should never reach the GPU."""
    pass


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------
@dataclass
class TaskContext:
    """Structured payload a caller hands to run(). Never a pre-built prompt
    string — context_builder is the only thing that renders final text."""
    variables: Dict[str, Any] = field(default_factory=dict)
    images: List[Any] = field(default_factory=list)  # list of PIL.Image, or empty

    def get(self, key, default=None):
        return self.variables.get(key, default)


@dataclass
class TaskResult:
    task_name: str
    success: bool
    parsed_output: Optional[Dict[str, Any]]
    raw_model_output: str
    prompt_version: str
    prompt_hash: str
    model_adapter_id: str
    inference_time: float
    retry_count: int
    validation_errors: List[str] = field(default_factory=list)
    token_counts: Optional[dict] = None
    fallback_reason: Optional[str] = None  # passed through unchanged if dispatched by fallback_dispatcher


class PromptManager:
    def __init__(self, adapter: ModelAdapter, max_new_tokens: int = 768):
        self.adapter = adapter
        self.max_new_tokens = max_new_tokens

    def run(self, task_name: str, context: TaskContext,
            fallback_reason: Optional[str] = None) -> TaskResult:
        spec = task_registry.get_task(task_name)  # raises KeyError for unknown task
        contract = output_contract.get_contract(spec.output_contract_name)

        self._validate_context(spec, context)  # raises MissingContextError before any GPU call

        template_text = self._load_template(spec)
        render_vars = dict(context.variables)
        for opt_var in spec.optional_context_vars:
            render_vars.setdefault(opt_var, None)  # rendered as "(none)" by context_builder
        # Cross-cutting language-preservation vars (language milestone):
        # every task's template may reference these to keep extracted
        # content in the source textbook's language. Defaulted centrally
        # here -- rather than added to each TaskSpec's declared context --
        # because they apply uniformly to every task, not just some; callers
        # (semantic_processor._run_task) normally supply the real detected
        # values, this default only matters for direct/low-level callers
        # (e.g. tests) that don't.
        render_vars.setdefault("target_language_name", "English")
        render_vars.setdefault("target_language_code", "en")
        prompt_text = context_builder.render(template_text, render_vars)
        prompt_hash = hashlib.sha1(template_text.encode()).hexdigest()[:10]

        images = context.images if spec.expects_images else []

        retry_count = 0
        last_response = None
        last_errors: List[str] = ["not attempted"]
        t0 = time.time()

        for attempt in range(2):  # one initial attempt + one internal retry, per frozen design
            retry_count = attempt
            response = self.adapter.generate_json(prompt_text, images=images,
                                                    max_new_tokens=self.max_new_tokens)
            last_response = response
            if not response.success or response.parsed_output is None:
                last_errors = [response.error_message or "adapter returned no parsed output"]
            else:
                normalized = output_contract.normalize_single_field_response(contract, response.parsed_output)
                is_valid, errors = output_contract.validate(contract, normalized)
                last_errors = errors
                if is_valid:
                    response.parsed_output = normalized
                    break
            if attempt == 0:
                logger.warning("Task '%s' failed validation on attempt 1 (%s) — retrying once.",
                                task_name, last_errors)

        success = (last_response is not None and last_response.success
                   and last_response.parsed_output is not None and not last_errors)
        inference_time = round(time.time() - t0, 3)

        result = TaskResult(
            task_name=task_name,
            success=success,
            parsed_output=last_response.parsed_output if (success and last_response) else None,
            raw_model_output=last_response.raw_output if last_response else "",
            prompt_version=spec.current_version,
            prompt_hash=prompt_hash,
            model_adapter_id=getattr(self.adapter, "adapter_id", "unknown-adapter"),
            inference_time=inference_time,
            retry_count=retry_count,
            validation_errors=[] if success else last_errors,
            token_counts=self.adapter.token_counts(),
            fallback_reason=fallback_reason,
        )

        logger.info(
            "task=%s success=%s prompt_version=%s prompt_hash=%s adapter=%s "
            "inference_time=%.3fs retry_count=%d fallback_reason=%s",
            task_name, success, spec.current_version, prompt_hash, result.model_adapter_id,
            inference_time, retry_count, fallback_reason,
        )
        return result

    # -- internals ----------------------------------------------------------
    def _validate_context(self, spec: "task_registry.TaskSpec", context: TaskContext) -> None:
        missing = [v for v in spec.required_context_vars if v not in context.variables]
        if missing:
            raise MissingContextError(
                f"Task '{spec.name}' (template {spec.current_version}) is missing required "
                f"context variable(s): {missing}. Declared required vars: {spec.required_context_vars}")
        if spec.expects_images and not context.images:
            logger.warning("Task '%s' expects image(s) but none were supplied in TaskContext.", spec.name)

    def _load_template(self, spec: "task_registry.TaskSpec") -> str:
        path = spec.template_path()
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


# ---------------------------------------------------------------------------
# Module-level convenience function, so callers can do
# `from prompt_manager import prompt_manager as pm; pm.run(...)` style usage
# once a manager singleton is configured — kept thin, no hidden state beyond
# whatever the caller constructs a PromptManager with.
# ---------------------------------------------------------------------------
def run(manager: PromptManager, task_name: str, context: TaskContext,
        fallback_reason: Optional[str] = None) -> TaskResult:
    return manager.run(task_name, context, fallback_reason=fallback_reason)