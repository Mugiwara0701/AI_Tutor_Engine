"""
teacher_knowledge_base/context.py — M6.1 (remediated)

TKBContext: shared mutable build state passed through all pipeline stages.
Updated to expose tkb_id, chapter_number, and metadata fields directly.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .metadata import TKBMetadata, TKBCompilerInfo

logger = logging.getLogger("teacher_knowledge_base.context")


class TKBDiagnostics:
    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.ambiguities: List[Dict[str, str]] = []

    def add_error(self, stage: str, message: str, detail: str = "") -> None:
        self.errors.append({"stage": stage, "message": message, "detail": detail})
        logger.error("TKB [%s] ERROR: %s%s", stage, message, f" — {detail}" if detail else "")

    def add_warning(self, stage: str, message: str, detail: str = "") -> None:
        self.warnings.append({"stage": stage, "message": message, "detail": detail})
        logger.warning("TKB [%s] WARNING: %s%s", stage, message, f" — {detail}" if detail else "")

    def add_ambiguity(self, spec_reference: str, description: str) -> None:
        self.ambiguities.append({"spec_reference": spec_reference, "description": description})
        logger.warning("TKB ARCHITECTURAL AMBIGUITY in %r: %s", spec_reference, description)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "ambiguity_count": len(self.ambiguities),
            "errors": self.errors,
            "warnings": self.warnings,
            "ambiguities": self.ambiguities,
        }


class TKBContext:
    """Shared mutable build context. Orchestrator fills it; builders read+write it."""

    def __init__(
        self,
        compiler_artifacts: Dict[str, Any],
        metadata: TKBMetadata,
        compiler_information: TKBCompilerInfo,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._compiler_artifacts = compiler_artifacts
        self._metadata = metadata
        self._compiler_information = compiler_information
        self._config: Dict[str, Any] = config or {}
        self._outputs: Dict[str, Any] = {}
        self._diagnostics = TKBDiagnostics()
        self._stage_timings: Dict[str, float] = {}
        self._completed_stages: List[str] = []

    # --- Immutable inputs ---------------------------------------------------

    @property
    def compiler_artifacts(self) -> Dict[str, Any]:
        return self._compiler_artifacts

    @property
    def metadata(self) -> TKBMetadata:
        return self._metadata

    @property
    def compiler_information(self) -> TKBCompilerInfo:
        return self._compiler_information

    @property
    def tkb_id(self) -> str:
        return self._metadata.tkb_id

    @property
    def chapter_number(self) -> int:
        return self._metadata.chapter_number

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def diagnostics(self) -> TKBDiagnostics:
        return self._diagnostics

    # --- Stage output management --------------------------------------------

    def set_output(self, stage: str, output: Any) -> None:
        self._outputs[stage] = output
        if stage not in self._completed_stages:
            self._completed_stages.append(stage)

    def get_output(self, stage: str) -> Optional[Any]:
        return self._outputs.get(stage)

    def require_output(self, stage: str, requesting_stage: str) -> Any:
        from .exceptions import TKBBuilderError
        output = self._outputs.get(stage)
        if output is None:
            raise TKBBuilderError(
                requesting_stage,
                f"Required output from stage {stage!r} not available. "
                f"Ensure pipeline order is correct.",
            )
        return output

    @property
    def completed_stages(self) -> List[str]:
        return list(self._completed_stages)

    @property
    def outputs(self) -> Dict[str, Any]:
        return dict(self._outputs)

    # --- Timing tracking ----------------------------------------------------

    def record_stage_timing(self, stage: str, elapsed_seconds: float) -> None:
        self._stage_timings[stage] = round(elapsed_seconds, 4)

    @property
    def stage_timings(self) -> Dict[str, float]:
        return dict(self._stage_timings)

    # --- Configuration helpers ----------------------------------------------

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def is_strict_validation(self) -> bool:
        return bool(self._config.get("strict_validation", False))
