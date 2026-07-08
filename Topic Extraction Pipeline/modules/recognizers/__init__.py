"""
modules/recognizers — Educational-Object-Aware recognizers for Stage D.

This package replaces subject-name-based routing ("if subject ==
'Physics'") with block-type-based routing ("if Stage B said Formula Box,
try these recognizers"). Stage B already tells Stage D WHAT KIND of block
this is; this package decides, per block type, WHICH reusable-knowledge
shape it's most likely to be, and extracts it.

Public API (used by modules/stage_d_extraction.py):
    candidates_for(block_type: str) -> List[Recognizer]

To add a new educational object type:
    1. Add a new Recognizer subclass (in an existing file here, or a new
       one) implementing `recognize(block)` and, if it should ever fall
       back to the VLM, either inherit FormulaFamilyRecognizer /
       VisualFamilyRecognizer or override `vlm_fallback` directly.
    2. Instantiate it and `register(...)` it below against whichever
       Stage B block_type(s) it's a candidate for.
No change to stage_d_extraction.py or to any other recognizer is needed.
"""
from modules.recognizers.registry import register, candidates_for, registered_block_types

from modules.recognizers.formula_recognizers import (
    FormulaRecognizer, MathIdentityRecognizer, ChemicalReactionRecognizer, EconomicIdentityRecognizer,
)
from modules.recognizers.procedure_recognizers import (
    ProcedureRecognizer, AlgorithmRecognizer, JournalProcedureRecognizer,
)
from modules.recognizers.programming_recognizers import ProgrammingSyntaxRecognizer, PseudocodeRecognizer
from modules.recognizers.accounting_recognizers import (
    JournalFormatRecognizer, LedgerRecognizer, AccountingRuleRecognizer,
)
from modules.recognizers.visual_recognizers import (
    FlowchartRecognizer, GraphRecognizer, CircuitDiagramRecognizer, ConceptTableRecognizer,
    GenericVisualRecognizer,
)
from modules.recognizers.concept_recognizers import DefinitionRecognizer

# One shared instance per recognizer (they're stateless) — reused across
# every block_type list it's registered under.
_formula = FormulaRecognizer()
_math_identity = MathIdentityRecognizer()
_chemical_reaction = ChemicalReactionRecognizer()
_economic_identity = EconomicIdentityRecognizer()

_procedure = ProcedureRecognizer()
_algorithm = AlgorithmRecognizer()
_journal_procedure = JournalProcedureRecognizer()

_programming_syntax = ProgrammingSyntaxRecognizer()
_pseudocode = PseudocodeRecognizer()

_journal_format = JournalFormatRecognizer()
_ledger = LedgerRecognizer()
_accounting_rule = AccountingRuleRecognizer()

_flowchart = FlowchartRecognizer()
_graph = GraphRecognizer()
_circuit_diagram = CircuitDiagramRecognizer()
_concept_table = ConceptTableRecognizer()
_generic_visual = GenericVisualRecognizer()

_definition = DefinitionRecognizer()

# --- Formula Box: reusable formula / identity family --------------------
register(_formula, ["Formula Box", "Worked Example"])
register(_math_identity, ["Formula Box", "Worked Example"])
register(_chemical_reaction, ["Formula Box", "Worked Example"])
register(_economic_identity, ["Formula Box", "Worked Example"])

# --- Worked Example: procedure family (formula recognizers above are
#     also candidates here, e.g. a worked example that's really just a
#     restated formula with no explicit steps) ---------------------------
register(_procedure, ["Worked Example"])
register(_journal_procedure, ["Worked Example"])
register(_algorithm, ["Worked Example", "Programming Syntax"])

# --- Programming Syntax --------------------------------------------------
register(_programming_syntax, ["Programming Syntax"])
register(_pseudocode, ["Programming Syntax"])

# --- Accounting Format (and accounting-shaped Tables) --------------------
register(_journal_format, ["Accounting Format", "Table"])
register(_ledger, ["Accounting Format", "Table"])
register(_accounting_rule, ["Accounting Format"])

# --- Visual family: Flowchart / Decision Tree / Diagram / Figure / Table -
register(_flowchart, ["Flowchart", "Diagram", "Decision Tree"])
register(_graph, ["Figure", "Diagram"])
register(_circuit_diagram, ["Diagram", "Figure"])
register(_concept_table, ["Table"])
register(_generic_visual, [
    "Table", "Figure", "Diagram", "Flowchart", "Decision Tree",
    "Programming Syntax", "Accounting Format",
])

# --- Definition -----------------------------------------------------------
register(_definition, ["Definition"])

__all__ = ["register", "candidates_for", "registered_block_types"]
