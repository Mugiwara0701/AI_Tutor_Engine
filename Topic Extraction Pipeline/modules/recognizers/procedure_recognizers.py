"""
modules/recognizers/procedure_recognizers.py — candidate recognizers for
"Worked Example" blocks (and, for AlgorithmRecognizer, also "Programming
Syntax" blocks): reusable step-by-step procedure, algorithm, and
journal-entry procedure. These are the recognizers most directly
responsible for the "keep reusable knowledge, discard substitutions /
arithmetic / final answers" requirement — a Worked Example almost always
contains BOTH a reusable procedure AND numeric substitutions, and these
recognizers are what separates the two.
"""
import re
from typing import List, Optional

from modules.stage_a_geometry import Block
from modules.stage_b_classify import _NUMERIC_SUBSTITUTION_RE
from modules.recognizers.base import FormulaFamilyRecognizer, RecognitionResult, block_raw_texts

_STEP_RE = re.compile(r"^\s*(step\s*\d+|[0-9]+[.)]|first(?:ly)?|then|next|finally)\b", re.I)
_ALGO_KEYWORDS_RE = re.compile(r"\b(input|output|repeat|while|if\s+.+\s+then|algorithm|pseudocode)\b", re.I)
_JOURNAL_KEYWORDS_RE = re.compile(r"\b(dr\.?|cr\.?|debit|credit|journal entry|ledger)\b", re.I)
_PURELY_SYMBOLIC_RE = re.compile(r"^[^a-zA-Z]*$")


def _non_numeric_lines(texts: List[str]) -> List[str]:
    """Drops lines that are just a numeric substitution/arithmetic step
    (e.g. "= 3.14 * 2 * 5", "= 31.4 cm"), keeping the ones that carry
    actual reusable procedural language."""
    return [t for t in texts if t and not _NUMERIC_SUBSTITUTION_RE.match(t.strip())]


class ProcedureRecognizer(FormulaFamilyRecognizer):
    """Worked Example -> keeps the reusable step/procedure text (lines
    that read as an explicit step, e.g. "Step 1: ...", "1) ...",
    "First, ..."), discards numeric-substitution and bare-arithmetic
    lines from those steps."""
    name = "procedure"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        step_lines = [t for t in texts if _STEP_RE.match(t)]
        if not step_lines:
            return None

        kept = _non_numeric_lines(step_lines)
        if not kept:
            return None

        discarded = len(texts) - len(kept)
        return RecognitionResult(
            confidence=0.75,
            data={
                "reusable_procedure": " | ".join(kept),
                "procedure_steps": kept,
                "discarded_substitutions_count": discarded,
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class AlgorithmRecognizer(FormulaFamilyRecognizer):
    """Recognizes algorithmic/pseudocode-flavored procedures (Input/
    Output/Repeat/While/If-Then/"algorithm") wherever they appear — inside
    a Worked Example walkthrough, or as the primary content of a
    Programming Syntax block."""
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
    """Recognizes journal-entry procedure text inside a Worked Example
    (e.g. accounting numericals that walk through "Debit X, Credit Y,
    being ..."), keeping the rule/procedure language and discarding the
    posted amounts."""
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
