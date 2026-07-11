"""
build_metadata/configuration_metadata.py — Phase E1: ConfigurationMetadata.

ConfigurationMetadata is the DETERMINISTIC half of BuildMetadata's
operational/deterministic split: every field here is a static
configuration value (config.py env-backed constants, prompt template
versions from prompt_manager/task_registry.py's own TASKS registry) --
never a wall-clock timestamp, a run identifier, or anything else that
would vary between two runs made with the same configuration. That
determinism is exactly what makes a single ConfigurationMetadata
fingerprint meaningful: two chapters compiled with the same
configuration must produce the same fingerprint, regardless of when or
in what order they were compiled.

REUSE, DON'T RECOMPUTE: the fingerprint below is derived using
canonicalization.py's own canonical_json()/sha256_hexdigest() -- the
exact same shared canonicalization primitives compiler/fingerprints.py,
knowledge_graph/fingerprints.py, and validation/determinism.py already
use. No second fingerprint implementation is introduced here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict

import config
from canonicalization import canonical_json, sha256_hexdigest
from prompt_manager.task_registry import TASKS

# This module's own version marker -- independent of every other *_VERSION
# constant in this codebase (see e.g. compiler/finalize.py's own
# FINALIZE_VERSION). Bump only if the SHAPE this module produces changes
# in a way a consumer should be able to detect.
CONFIGURATION_METADATA_VERSION = "E1.1"


def _compiler_config() -> Dict[str, Any]:
    """Compiler-level configuration knobs (config.py), read-only."""
    return {
        "default_page_batch_size": config.DEFAULT_PAGE_BATCH_SIZE,
        "min_page_batch_size": config.MIN_PAGE_BATCH_SIZE,
        "max_page_batch_size": config.MAX_PAGE_BATCH_SIZE,
        "max_semantic_description_words": config.MAX_SEMANTIC_DESCRIPTION_WORDS,
        "schema_version": config.SCHEMA_VERSION,
    }


def _model_config() -> Dict[str, Any]:
    """VLM model configuration (config.py), read-only."""
    return {
        "vlm_model_id": config.VLM_MODEL_ID,
        "vlm_use_4bit": config.VLM_USE_4BIT,
        "vlm_max_new_tokens": config.VLM_MAX_NEW_TOKENS,
        "vlm_device": config.VLM_DEVICE,
    }


def _prompt_versions() -> Dict[str, str]:
    """task-name -> that task's own current_version, read directly from
    prompt_manager/task_registry.py's own TASKS registry -- never a
    second, independently-maintained copy of these versions."""
    return {name: spec.current_version for name, spec in sorted(TASKS.items())}


def _extraction_policy() -> Dict[str, Any]:
    """Extraction-policy-relevant configuration (config.py), read-only.
    This codebase has no dedicated "extraction policy version" constant
    (unlike ENRICHMENT_VERSION/NORMALIZATION_VERSION/etc., each of which
    versions an actual pass) -- so, per the task's own REUSE, DON'T
    RECOMPUTE / DO NOT duplicate-or-invent-new-version-fields rule,
    this surfaces the actual policy VALUES rather than fabricating a
    version number no other module defines."""
    return {
        "deterministic_confidence_floor": config.DETERMINISTIC_CONFIDENCE_FLOOR,
        "enable_visual_vlm": config.ENABLE_VISUAL_VLM,
    }


def _deterministic_thresholds() -> Dict[str, Any]:
    return {
        "deterministic_confidence_floor": config.DETERMINISTIC_CONFIDENCE_FLOOR,
    }


def _feature_flags() -> Dict[str, Any]:
    return {
        "vlm_use_4bit": config.VLM_USE_4BIT,
        "enable_visual_vlm": config.ENABLE_VISUAL_VLM,
        "export_blocks": config.EXPORT_BLOCKS,
        "debug_mode": config.DEBUG_MODE,
    }


@dataclass
class ConfigurationMetadata:
    """The full Phase E1 ConfigurationMetadata artifact. Purely a data
    holder; all aggregation happens in generate_configuration_metadata()
    below."""

    generated_at: str
    configuration_metadata_version: str
    compiler_config: Dict[str, Any]
    model_config: Dict[str, Any]
    prompt_versions: Dict[str, str]
    extraction_policy: Dict[str, Any]
    deterministic_thresholds: Dict[str, Any]
    feature_flags: Dict[str, Any]
    configuration_fingerprint: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_configuration_metadata() -> Dict[str, Any]:
    """Phase E1: builds this chapter's ConfigurationMetadata and its one
    deterministic configuration fingerprint. Every input is a static
    configuration value (config.py, prompt_manager/task_registry.py) --
    nothing here depends on `pdf_path`, wall-clock time, or any other
    per-run/per-chapter operational detail (that is CompilationMetadata's
    job, kept strictly separate -- see this package's own module
    docstring and compilation_metadata.py's own "NEVER PARTICIPATES IN
    ANY FINGERPRINT" note).

    The fingerprint is computed over exactly the five deterministic
    blocks below (compiler_config, model_config, prompt_versions,
    extraction_policy, deterministic_thresholds, feature_flags) via
    canonicalization.py's canonical_json()/sha256_hexdigest() -- the same
    primitives every other fingerprint in this codebase already uses --
    and deliberately excludes `generated_at` (canonicalization.py's own
    VOLATILE_KEYS already strips it, same as every other fingerprinted
    artifact in this codebase) and excludes itself
    (`configuration_fingerprint` is the fingerprint's own output, not an
    input to it)."""
    compiler_config = _compiler_config()
    model_config = _model_config()
    prompt_versions = _prompt_versions()
    extraction_policy = _extraction_policy()
    deterministic_thresholds = _deterministic_thresholds()
    feature_flags = _feature_flags()

    fingerprint_payload = {
        "compiler_config": compiler_config,
        "model_config": model_config,
        "prompt_versions": prompt_versions,
        "extraction_policy": extraction_policy,
        "deterministic_thresholds": deterministic_thresholds,
        "feature_flags": feature_flags,
    }
    configuration_fingerprint = sha256_hexdigest(canonical_json(fingerprint_payload))

    metadata = ConfigurationMetadata(
        generated_at=datetime.now(timezone.utc).isoformat(),
        configuration_metadata_version=CONFIGURATION_METADATA_VERSION,
        compiler_config=compiler_config,
        model_config=model_config,
        prompt_versions=prompt_versions,
        extraction_policy=extraction_policy,
        deterministic_thresholds=deterministic_thresholds,
        feature_flags=feature_flags,
        configuration_fingerprint=configuration_fingerprint,
    )
    return metadata.to_dict()