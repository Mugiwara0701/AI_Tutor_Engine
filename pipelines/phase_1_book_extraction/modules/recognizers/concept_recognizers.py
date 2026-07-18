"""
modules/recognizers/concept_recognizers.py — the candidate recognizer for
"Definition" blocks.

M4.1D improvements:
  - Extended regex coverage for definition patterns
  - Multi-line definition continuation handling
  - Additional definition sentence shapes ("denotes", "by X we mean")
  - Term quality validation
  - Improved confidence scoring based on match quality
"""
import re
from typing import List, Optional

from modules.stage_a_geometry import Block
from modules.recognizers.base import Recognizer, RecognitionResult, block_raw_texts

# Import shared patterns from text_utils (M4.1A infrastructure).
# These are the authoritative definition patterns.
from modules.text_utils import (
    DEFINITION_TERM_FIRST_RE,
    DEFINITION_TERM_AFTER_RE,
    DEFINITION_TERM_DENOTES_RE,
    DEFINITION_TERM_BY_MEAN_RE,
    TERM_STOPWORDS,
    term_is_valid,
)

# M4.1D: Additional definition body patterns (deterministic).
_DEFINITION_CONTINUATION_RE = re.compile(
    r"^\s*(?:that is|i\.e\.|in other words|which means|meaning)\b", re.I
)

# M4.1D: Pattern for multi-line definition continuation.
# Lines that start with lowercase and don't start a new sentence are
# likely continuation of the previous definition.
_CONTINUATION_LINE_RE = re.compile(r"^[a-z]")

# M4.1D: Pattern for definition delimiters (colon after term).
_COLON_DEFINITION_RE = re.compile(
    r"^(?P<term>[A-Z][A-Za-z .\-]{1,38})\s*[:—–]\s+\S"
)


class DefinitionRecognizer(Recognizer):
    """M4.1D improved: Extended definition recognition with multiple
    sentence patterns, continuation handling, and multi-line support."""
    name = "definition"
    educational_object_type = "concept"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        meta = block.grouping_meta or {}
        term = meta.get("candidate_term", "")
        texts = block_raw_texts(block)
        body = " ".join(texts)

        # M4.1D: Try multiple definition patterns for better coverage
        confidence = 0.75  # base confidence
        definition_type = "standard"
        additional_terms = meta.get("additional_terms", [])

        if term:
            # Term already extracted by Stage A — validate it
            if not term_is_valid(term):
                return RecognitionResult(
                    confidence=0.3,
                    data={"term": term, "definition_type": "weak"},
                    educational_object_type=self.educational_object_type,
                    recognizer_name=self.name,
                )

            # M4.1D: Boost confidence based on definition pattern match
            if DEFINITION_TERM_FIRST_RE.match(body):
                confidence = 0.85
                definition_type = "is_defined_as"
            elif DEFINITION_TERM_AFTER_RE.search(body):
                confidence = 0.8
                definition_type = "is_called"
            elif DEFINITION_TERM_DENOTES_RE.search(body):
                confidence = 0.8
                definition_type = "denotes"
            elif DEFINITION_TERM_BY_MEAN_RE.search(body):
                confidence = 0.8
                definition_type = "by_mean"
            elif _COLON_DEFINITION_RE.match(body):
                confidence = 0.65
                definition_type = "colon_delimited"
        else:
            # M4.1D: No term from Stage A — try extracting from body text
            term = self._extract_term_from_body(body)
            if term:
                confidence = 0.6
                definition_type = "body_extracted"
            else:
                return None  # No term found at all

        # M4.1D: Multi-line definition handling
        continuation_count = self._count_continuation_lines(texts)
        if continuation_count > 0:
            confidence = min(1.0, confidence + 0.05)  # Multi-line definitions are more reliable

        # M4.1D: Grouped definitions from M4.1B
        if meta.get("grouped_definitions"):
            confidence = min(1.0, confidence + 0.05)

        data = {
            "term": term,
            "definition_type": definition_type,
        }
        if additional_terms:
            data["additional_terms"] = additional_terms
        if continuation_count > 0:
            data["continuation_lines"] = continuation_count

        return RecognitionResult(
            confidence=confidence,
            data=data,
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )

    def _extract_term_from_body(self, body: str) -> str:
        """M4.1D: Try to extract a definition term from body text using
        multiple pattern families."""
        for pattern in [DEFINITION_TERM_FIRST_RE, DEFINITION_TERM_DENOTES_RE,
                        DEFINITION_TERM_BY_MEAN_RE]:
            m = pattern.match(body) if hasattr(pattern, 'match') else None
            if m and "term" in m.groupdict():
                term = m.group("term").strip()
                if term_is_valid(term):
                    return term

        # Try search (not just match) for after-patterns
        m = DEFINITION_TERM_AFTER_RE.search(body)
        if m and "term" in m.groupdict():
            term = m.group("term").strip()
            if term_is_valid(term):
                return term

        # M4.1D: Colon-delimited pattern
        m = _COLON_DEFINITION_RE.match(body)
        if m:
            term = m.group("term").strip()
            if term_is_valid(term):
                return term

        return ""

    def _count_continuation_lines(self, texts: list) -> int:
        """M4.1D: Count continuation lines in a multi-line definition."""
        if len(texts) <= 1:
            return 0
        count = 0
        for text in texts[1:]:
            stripped = text.strip()
            if not stripped:
                continue
            if _DEFINITION_CONTINUATION_RE.match(stripped):
                count += 1
            elif _CONTINUATION_LINE_RE.match(stripped):
                count += 1
        return count
