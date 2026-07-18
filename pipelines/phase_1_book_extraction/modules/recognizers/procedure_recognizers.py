"""
modules/recognizers/procedure_recognizers.py — candidate recognizers for
"Worked Example" blocks (and, for AlgorithmRecognizer, also "Programming
Syntax" blocks): reusable step-by-step procedure, algorithm, and
journal-entry procedure.

M4.1D improvements:
  - Improved worked example detection
  - Cross-page example continuation support
  - Better step marker detection (using shared STEP_MARKER_RE)
  - Improved numeric substitution filtering
"""
import re
from typing import List, Optional

from modules.stage_a_geometry import Block
from modules.stage_b_classify import _NUMERIC_SUBSTITUTION_RE
from modules.recognizers.base import FormulaFamilyRecognizer, RecognitionResult, block_raw_texts
from modules.text_utils import STEP_MARKER_RE, partial_match_confidence

_ALGO_KEYWORDS_RE = re.compile(r"\b(input|output|repeat|while|if\s+.+\s+then|algorithm|pseudocode)\b", re.I)
_JOURNAL_KEYWORDS_RE = re.compile(r"\b(dr\.?|cr\.?|debit|credit|journal entry|ledger)\b", re.I)
_PURELY_SYMBOLIC_RE = re.compile(r"^[^a-zA-Z]*$")

# M4.1D: Solution / answer patterns for worked example continuation.
_SOLUTION_RE = re.compile(r"^\s*(solution|answer|method|approach)\b", re.I)

# M4.1D: "Given" / "Find" / "To prove" patterns common in worked examples.
_GIVEN_FIND_RE = re.compile(r"^\s*(given|find|to prove|to show|required|prove that)\b", re.I)


def _non_numeric_lines(texts: List[str]) -> List[str]:
    """Drops lines that are just a numeric substitution/arithmetic step."""
    return [t for t in texts if t and not _NUMERIC_SUBSTITUTION_RE.match(t.strip())]


class ProcedureRecognizer(FormulaFamilyRecognizer):
    """Worked Example -> keeps the reusable step/procedure text.

    M4.1D improvements:
    - Uses shared STEP_MARKER_RE from text_utils
    - Supports Solution/Answer/Given/Find markers
    - Better confidence via partial_match_confidence
    - Cross-page continuation awareness
    """
    name = "procedure"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        # M4.1D: Use shared STEP_MARKER_RE + solution/given markers
        step_lines = [t for t in texts if STEP_MARKER_RE.match(t)]
        solution_lines = [t for t in texts if _SOLUTION_RE.match(t)]
        given_lines = [t for t in texts if _GIVEN_FIND_RE.match(t)]

        matched_lines = step_lines + solution_lines + given_lines
        if not matched_lines and not step_lines:
            return None

        kept = _non_numeric_lines(matched_lines if matched_lines else step_lines)
        if not kept:
            return None

        discarded = len(texts) - len(kept)

        # M4.1D: Better confidence scoring
        confidence = partial_match_confidence(len(kept), len(texts), 0.75)
        if solution_lines or given_lines:
            confidence = max(confidence, 0.7)  # Solution/Given markers boost confidence

        # M4.1D: Cross-page continuation awareness
        meta = block.grouping_meta or {}
        data = {
            "reusable_procedure": " | ".join(kept),
            "procedure_steps": kept,
            "discarded_substitutions_count": discarded,
        }
        if meta.get("continuation"):
            data["cross_page"] = True
            confidence = min(1.0, confidence + 0.05)

        return RecognitionResult(
            confidence=confidence,
            data=data,
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class AlgorithmRecognizer(FormulaFamilyRecognizer):
    """Recognizes algorithmic/pseudocode-flavored procedures."""
    name = "algorithm"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        if not any(_ALGO_KEYWORDS_RE.search(t) for t in texts):
            return None

        kept = _non_numeric_lines(texts)
        if not kept:
            return None

        return RecognitionResult(
            confidence=0.78,
            data={
                "reusable_procedure": " | ".join(kept),
                "procedure_steps": kept,
                "procedure_type": "algorithm",
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class JournalProcedureRecognizer(FormulaFamilyRecognizer):
    """Recognizes journal-entry procedure text inside a Worked Example."""
    name = "journal_procedure"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        hits = [t for t in texts if _JOURNAL_KEYWORDS_RE.search(t)]
        if not hits:
            return None

        kept = [t for t in hits if not _PURELY_SYMBOLIC_RE.match(t)]
        if not kept:
            return None

        return RecognitionResult(
            confidence=0.72,
            data={
                "reusable_procedure": " | ".join(kept),
                "procedure_steps": kept,
                "procedure_type": "journal_entry_rule",
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class WorkedExampleRecognizer(FormulaFamilyRecognizer):
    """M4.1D: Dedicated worked-example recognizer that detects
    Solution/Answer/Given/Find structure without requiring explicit
    step markers. Catches worked examples that the ProcedureRecognizer
    misses because they use prose rather than numbered steps."""
    name = "worked_example"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        has_solution = any(_SOLUTION_RE.match(t) for t in texts)
        has_given = any(_GIVEN_FIND_RE.match(t) for t in texts)

        if not has_solution and not has_given:
            return None

        kept = _non_numeric_lines(texts)
        if not kept:
            return None

        confidence = 0.7
        if has_solution and has_given:
            confidence = 0.8

        return RecognitionResult(
            confidence=confidence,
            data={
                "reusable_procedure": " | ".join(kept),
                "procedure_steps": kept,
                "procedure_type": "worked_example",
                "has_solution": has_solution,
                "has_given": has_given,
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
