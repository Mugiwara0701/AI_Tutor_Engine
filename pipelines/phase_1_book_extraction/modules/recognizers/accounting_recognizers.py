"""
modules/recognizers/accounting_recognizers.py — candidate recognizers for
"Accounting Format" (and, for the table-shaped ones, "Table") blocks:
journal-entry column format, ledger (T-account) structure, and the
golden rules of accounting. Each keeps the reusable FORMAT/RULE, never
the posted amounts.
"""
import re
from typing import Optional

from modules.stage_a_geometry import Block
from modules.recognizers.base import VisualFamilyRecognizer, RecognitionResult, block_raw_texts

_JOURNAL_FORMAT_HEADER_RE = re.compile(r"\b(date|particulars?|l\.?\s?f\.?|debit|credit|amount)\b", re.I)
_LEDGER_HEADER_RE = re.compile(r"\b(dr\.?|cr\.?)\b.*\b(ledger|account)\b", re.I)
_GOLDEN_RULE_RE = re.compile(
    r"\b(debit the receiver|credit the giver|debit what comes in|credit what goes out|"
    r"debit all expenses(?: and losses)?|credit all incomes?(?: and gains)?)\b", re.I)


class JournalFormatRecognizer(VisualFamilyRecognizer):
    """Table/Accounting-Format blocks whose header row is a journal-entry
    template (Date / Particulars / L.F. / Debit / Credit) -- keeps the
    column format, discards the actual posted amounts (the amounts never
    even get read; only the header vocabulary matters here)."""
    name = "journal_format"
    educational_object_type = "accounting_format"
    use_table_semantics = True

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        header_texts = [t for t in block_raw_texts(block) if t and t.strip()][:4]
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        combined = " ".join(header_texts) + " " + caption
        hits = _JOURNAL_FORMAT_HEADER_RE.findall(combined)
        distinct = sorted(set(h.lower().replace(" ", "") for h in hits))
        if len(distinct) < 2:
            return None

        return RecognitionResult(
            confidence=0.75,
            data={"format_type": "journal_entry", "columns": distinct},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class LedgerRecognizer(VisualFamilyRecognizer):
    """Recognizes a ledger / T-account structure by its characteristic
    Dr./Cr. + "ledger"/"account" header vocabulary."""
    name = "ledger"
    educational_object_type = "accounting_format"
    use_table_semantics = True

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        body = " ".join(t for t in block_raw_texts(block) if t)
        caption = (block.grouping_meta or {}).get("caption", "") or ""
        if not _LEDGER_HEADER_RE.search(f"{body} {caption}"):
            return None

        return RecognitionResult(
            confidence=0.7,
            data={"format_type": "ledger_t_account"},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )


class AccountingRuleRecognizer(VisualFamilyRecognizer):
    """Recognizes the golden rules of accounting (Debit the receiver /
    Credit the giver, etc.) — reusable rule text, never example-specific."""
    name = "accounting_rule"
    educational_object_type = "accounting_format"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        texts = [t for t in block_raw_texts(block) if t]
        hits = [t for t in texts if _GOLDEN_RULE_RE.search(t)]
        if not hits:
            return None

        return RecognitionResult(
            confidence=0.85,
            data={"format_type": "accounting_rule", "rules": hits},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
