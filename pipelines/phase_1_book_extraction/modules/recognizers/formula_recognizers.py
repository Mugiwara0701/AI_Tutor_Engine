"""
modules/recognizers/formula_recognizers.py — candidate recognizers for
"Formula Box" (and, for the plain FormulaRecognizer, "Worked Example")
blocks: general reusable formula, mathematical/trigonometric identity,
chemical reaction equation, economic identity.

M4.1D improvements:
  - Improved multiline equation support
  - Aligned equation detection
  - Continuation detection for split equations
  - Variable extraction from formula lines
  - Better confidence scoring
"""
import re
from typing import Dict, List, Optional, Set

from modules.stage_a_geometry import Block
from modules.stage_b_classify import _VARIABLE_ONLY_RE
from modules.recognizers.base import FormulaFamilyRecognizer, RecognitionResult, block_raw_texts
from modules.text_utils import partial_match_confidence

_TRIG_LOG_RE = re.compile(r"\b(sin|cos|tan|cot|sec|cosec|log|ln)\b", re.I)
_IDENTITY_HINT_RE = re.compile(r"\b(identity|identities)\b", re.I)
_IDENTITY_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s+\-*/^().]*=[A-Za-z0-9\s+\-*/^().]+$")

_CHEM_ARROW_RE = re.compile(r"(->|→|⇌|=>)")
_CHEM_FORMULA_TOKEN_RE = re.compile(r"[A-Z][a-z]?\d*")

_ECON_KEYWORDS_RE = re.compile(
    r"\b(GDP|GNP|NNP|NDP|MPC|MPS|APC|APS|elasticity|equilibrium|national income)\b", re.I)
_ECON_LHS_RE = re.compile(r"^\s*(GDP|GNP|NNP|NDP)\b", re.I)

# M4.1D: Equation continuation patterns (aligned equations).
_ALIGNMENT_MARKER_RE = re.compile(r"(&=|\\\\|\.\.\.)")
_CONTINUATION_OPERATOR_RE = re.compile(r"^\s*[=+\-*/]")

# M4.1D: Variable extraction pattern.
# Extracts single-letter variables (possibly with subscripts/superscripts).
_VARIABLE_RE = re.compile(r"\b([A-Za-z](?:_\{?[A-Za-z0-9]+\}?)?)\b")

# M4.1D: Common non-variable words to exclude from variable extraction.
_VARIABLE_STOPWORDS = frozenset({
    "sin", "cos", "tan", "cot", "sec", "cosec", "log", "ln",
    "if", "or", "is", "as", "by", "to", "of", "in", "on", "at",
    "and", "the", "for", "not", "mod", "div",
    "max", "min", "lim", "inf", "sup",
})


def _extract_variables(formula_text: str) -> List[str]:
    """M4.1D: Deterministically extract variable names from a formula line.
    Returns single-letter variables (with optional subscripts), excluding
    common function names and stopwords."""
    matches = _VARIABLE_RE.findall(formula_text)
    seen: Set[str] = set()
    variables: List[str] = []
    for v in matches:
        v_lower = v.lower()
        if v_lower in _VARIABLE_STOPWORDS:
            continue
        if len(v) == 1 and v_lower not in seen:
            seen.add(v_lower)
            variables.append(v)
        elif "_" in v and v not in seen:
            seen.add(v)
            variables.append(v)
    return variables


def _is_continuation_line(text: str) -> bool:
    """M4.1D: Check if a line is a continuation of a previous equation."""
    stripped = text.strip()
    return bool(_CONTINUATION_OPERATOR_RE.match(stripped) or
                _ALIGNMENT_MARKER_RE.search(stripped))


class FormulaRecognizer(FormulaFamilyRecognizer):
    """General-purpose reusable-formula recognizer.

    M4.1D improvements:
    - Multiline equation support (merged continuations from M4.1B)
    - Variable extraction
    - Better confidence scoring using partial_match_confidence
    """
    name = "formula"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        formula_lines = [t for t in texts if _VARIABLE_ONLY_RE.match(t)]

        # M4.1D: Also accept lines that are continuations of equations
        if not formula_lines:
            # Check if we have continuation lines that form a multiline equation
            continuation_lines = [t for t in texts if _is_continuation_line(t)]
            if continuation_lines and len(continuation_lines) >= len(texts) // 2:
                # Most lines are equation continuations — treat as formula
                formula_lines = texts
            else:
                return None

        discarded = [t for t in texts if t not in formula_lines]

        # M4.1D: Use partial_match_confidence for better scoring
        confidence = partial_match_confidence(len(formula_lines), len(texts), 0.85)

        # M4.1D: Extract variables from formula lines
        variables = []
        for line in formula_lines:
            variables.extend(_extract_variables(line))
        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_vars = []
        for v in variables:
            if v not in seen:
                seen.add(v)
                unique_vars.append(v)

        data = {
            "reusable_formula": formula_lines[0],
            "alternate_formula_forms": formula_lines[1:],
            "discarded_substitutions_count": len(discarded),
        }

        # M4.1D: Add extracted variables
        if unique_vars:
            data["variables"] = unique_vars

        # M4.1D: Flag multiline equations
        meta = block.grouping_meta or {}
        if meta.get("merged_continuation"):
            data["multiline_equation"] = True

        return RecognitionResult(
            confidence=confidence,
            data=data,
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class MathIdentityRecognizer(FormulaFamilyRecognizer):
    """Recognizes trigonometric/logarithmic identities.

    M4.1D improvements:
    - Better confidence scoring
    - Variable extraction
    """
    name = "math_identity"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        hits = [t for t in texts if _IDENTITY_SHAPE_RE.match(t) and _TRIG_LOG_RE.search(t)]
        if not hits:
            return None

        confidence = 0.9 if _IDENTITY_HINT_RE.search(" ".join(texts)) else 0.8

        # M4.1D: Extract variables
        variables = []
        for line in hits:
            variables.extend(_extract_variables(line))

        data = {
            "reusable_formula": hits[0],
            "alternate_formula_forms": hits[1:],
            "identity_type": "trigonometric_or_logarithmic",
        }
        if variables:
            data["variables"] = list(dict.fromkeys(variables))

        return RecognitionResult(
            confidence=confidence,
            data=data,
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class ChemicalReactionRecognizer(FormulaFamilyRecognizer):
    """Recognizes chemical reaction equations.

    M4.1D improvements:
    - Better letter/digit ratio filtering
    """
    name = "chemical_reaction"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        candidates = []
        for t in texts:
            if not _CHEM_ARROW_RE.search(t):
                continue
            if len(_CHEM_FORMULA_TOKEN_RE.findall(t)) < 2:
                continue
            letters = sum(c.isalpha() for c in t)
            digits = sum(c.isdigit() for c in t)
            if letters >= digits:
                candidates.append(t)
        if not candidates:
            return None

        return RecognitionResult(
            confidence=0.8,
            data={
                "reusable_formula": candidates[0],
                "alternate_formula_forms": candidates[1:],
                "reaction_type": "chemical_equation",
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class EconomicIdentityRecognizer(FormulaFamilyRecognizer):
    """Recognizes economics identities."""
    name = "economic_identity"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        hits = [t for t in texts if _VARIABLE_ONLY_RE.match(t) and _ECON_KEYWORDS_RE.search(t)]
        if not hits:
            hits = [t for t in texts if _VARIABLE_ONLY_RE.match(t) and _ECON_LHS_RE.match(t)]
        if not hits:
            return None

        # M4.1D: Extract variables
        variables = []
        for line in hits:
            variables.extend(_extract_variables(line))

        data = {
            "reusable_formula": hits[0],
            "alternate_formula_forms": hits[1:],
            "identity_type": "economic",
        }
        if variables:
            data["variables"] = list(dict.fromkeys(variables))

        return RecognitionResult(
            confidence=0.8,
            data=data,
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
