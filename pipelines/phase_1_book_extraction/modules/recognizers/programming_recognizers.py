"""
modules/recognizers/programming_recognizers.py — candidate recognizers for
"Programming Syntax" blocks: actual code (Python/C/etc.) and
natural-language pseudocode. Unlike a Worked Example, a programming-syntax
block generally IS the reusable artifact in full (there's no separate
"substitution" step to strip out) — these recognizers keep the whole
snippet rather than filtering line-by-line.
"""
import re
from typing import Optional

from modules.stage_a_geometry import Block
from modules.recognizers.base import VisualFamilyRecognizer, RecognitionResult, block_raw_texts

_CODE_HINT_RE = re.compile(
    r"(\bdef\s+\w+\s*\(|\bprint\s*\(|\bimport\s+\w+|\bfor\s+\w+\s+in\s+|#include|\bvoid\s+main|"
    r"\bclass\s+\w+|\breturn\b|;\s*$|\{|\})")
_PSEUDOCODE_HINT_RE = re.compile(r"\b(begin|end|procedure|function|input|output)\b", re.I)


class ProgrammingSyntaxRecognizer(VisualFamilyRecognizer):
    """Recognizes an actual code snippet by language-agnostic syntax
    tokens (def/print/import/for.../#include/braces/semicolons/...) and
    keeps it verbatim as reusable syntax reference."""
    name = "programming_syntax"
    educational_object_type = "programming_syntax"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        code_text = "\n".join(texts)
        if not _CODE_HINT_RE.search(code_text):
            return None

        return RecognitionResult(
            confidence=0.8,
            data={"reusable_syntax": code_text},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class PseudocodeRecognizer(VisualFamilyRecognizer):
    """Recognizes natural-language pseudocode (Begin/End, Procedure,
    Input/Output) that doesn't match a specific programming language's
    syntax but is still a reusable algorithmic template."""
    name = "pseudocode"
    educational_object_type = "programming_syntax"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        code_text = "\n".join(texts)
        if not _PSEUDOCODE_HINT_RE.search(code_text):
            return None

        return RecognitionResult(
            confidence=0.65,
            data={"reusable_syntax": code_text, "syntax_kind": "pseudocode"},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
