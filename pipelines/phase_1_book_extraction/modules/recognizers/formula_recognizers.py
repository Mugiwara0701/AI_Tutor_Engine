"""
modules/recognizers/formula_recognizers.py — candidate recognizers for
"Formula Box" (and, for the plain FormulaRecognizer, "Worked Example")
blocks: general reusable formula, mathematical/trigonometric identity,
chemical reaction equation, economic identity.

None of these branch on subject name. They differ only in WHAT PATTERN
the block's text matches — a chemical equation looks like
"element+element -> element", a trig identity contains sin/cos/tan/log
tokens, an economic identity contains GDP/MPC/... tokens — so a "Science"
book with unlabeled subjects still gets routed correctly per block, and a
book that mixes Physics formulae and Economics identities in the same
"Formula Box" style still gets each one recognized by the right
recognizer.
"""
import re
from typing import Optional

from modules.stage_a_geometry import Block
from modules.stage_b_classify import _VARIABLE_ONLY_RE
from modules.recognizers.base import FormulaFamilyRecognizer, RecognitionResult, block_raw_texts

_TRIG_LOG_RE = re.compile(r"\b(sin|cos|tan|cot|sec|cosec|log|ln)\b", re.I)
_IDENTITY_HINT_RE = re.compile(r"\b(identity|identities)\b", re.I)
# Unlike a plain reusable formula (_VARIABLE_ONLY_RE, which forbids digits
# on the right-hand side so it doesn't accidentally match a numeric
# substitution), a trig/algebraic IDENTITY often equals a small constant
# (sin^2(x) + cos^2(x) = 1) and its own exponents are digits too -- so
# this pattern allows digits on both sides, and relies on _TRIG_LOG_RE
# below (not "no digits") to keep it from matching bare arithmetic.
_IDENTITY_SHAPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s+\-*/^().]*=[A-Za-z0-9\s+\-*/^().]+$")

# A chemical equation reads as an arrow between element-shaped tokens
# (Capital letter, optional lowercase, optional digit/subscript), with
# more letters than digits overall (numeric-substitution / balancing
# coefficients don't dominate the line). Deliberately no \b anchors:
# adjacent element symbols in a formula like "NaCl" are not separated by
# a word boundary, so anchoring would only ever match the first token in
# each word.
_CHEM_ARROW_RE = re.compile(r"(->|→|⇌|=>)")
_CHEM_FORMULA_TOKEN_RE = re.compile(r"[A-Z][a-z]?\d*")

_ECON_KEYWORDS_RE = re.compile(
    r"\b(GDP|GNP|NNP|NDP|MPC|MPS|APC|APS|elasticity|equilibrium|national income)\b", re.I)
_ECON_LHS_RE = re.compile(r"^\s*(GDP|GNP|NNP|NDP)\b", re.I)


class FormulaRecognizer(FormulaFamilyRecognizer):
    """General-purpose reusable-formula recognizer. Ported unchanged from
    the pre-modular `_extract_formula_deterministic`: keeps only the
    variable-form line(s), discards numeric substitutions."""
    name = "formula"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        formula_lines = [t for t in texts if _VARIABLE_ONLY_RE.match(t)]
        if not formula_lines:
            return None

        discarded = [t for t in texts if t not in formula_lines]
        confidence = 0.85 if len(formula_lines) == 1 else 0.7
        return RecognitionResult(
            confidence=confidence,
            data={
                "reusable_formula": formula_lines[0],
                "alternate_formula_forms": formula_lines[1:],
                "discarded_substitutions_count": len(discarded),
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class MathIdentityRecognizer(FormulaFamilyRecognizer):
    """Recognizes trigonometric/logarithmic identities specifically.
    Scores slightly above the generic FormulaRecognizer when
    identity-specific vocabulary is present, so the registry's
    highest-confidence pick correctly favors the more specific match."""
    name = "math_identity"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t.strip() for t in block_raw_texts(block) if t and t.strip()]
        if not texts:
            return None

        hits = [t for t in texts if _IDENTITY_SHAPE_RE.match(t) and _TRIG_LOG_RE.search(t)]
        if not hits:
            return None

        confidence = 0.9 if _IDENTITY_HINT_RE.search(" ".join(texts)) else 0.8
        return RecognitionResult(
            confidence=confidence,
            data={
                "reusable_formula": hits[0],
                "alternate_formula_forms": hits[1:],
                "identity_type": "trigonometric_or_logarithmic",
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class ChemicalReactionRecognizer(FormulaFamilyRecognizer):
    """Recognizes a chemical reaction/equation line (elements + reaction
    arrow), keeping the reusable equation and discarding numeric-heavy
    lines (balancing coefficients dominated by digits, quantities in a
    worked calculation, etc.)."""
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
    """Recognizes economics identities (GDP = C + I + G + X - M,
    MPC + MPS = 1, ...) by economics-specific vocabulary/LHS tokens rather
    than by subject metadata."""
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

        return RecognitionResult(
            confidence=0.8,
            data={
                "reusable_formula": hits[0],
                "alternate_formula_forms": hits[1:],
                "identity_type": "economic",
            },
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
