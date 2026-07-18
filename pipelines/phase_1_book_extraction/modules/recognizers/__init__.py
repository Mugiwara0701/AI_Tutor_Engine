"""
modules/recognizers — Educational-Object-Aware recognizers for Stage D.

This package replaces subject-name-based routing ("if subject ==
'Physics'") with block-type-based routing ("if Stage B said Formula Box,
try these recognizers"). Stage B already tells Stage D WHAT KIND of block
this is; this package decides, per block type, WHICH reusable-knowledge
shape it's most likely to be, and extracts it.

Public API (used by modules/stage_d_extraction.py):
    candidates_for(block_type: str) -> List[Recognizer]

M4.1D: Added new recognizers:
  - WorkedExampleRecognizer (procedure_recognizers)
  - DiagramSubtypeRecognizer (visual_recognizers)
  - FigureWithCaptionRecognizer (visual_recognizers)
"""
from modules.recognizers.registry import register, candidates_for, registered_block_types

from modules.recognizers.formula_recognizers import (
    FormulaRecognizer, MathIdentityRecognizer, ChemicalReactionRecognizer, EconomicIdentityRecognizer,
)
from modules.recognizers.procedure_recognizers import (
    ProcedureRecognizer, AlgorithmRecognizer, JournalProcedureRecognizer,
    WorkedExampleRecognizer,
)
from modules.recognizers.programming_recognizers import ProgrammingSyntaxRecognizer, PseudocodeRecognizer
from modules.recognizers.accounting_recognizers import (
    JournalFormatRecognizer, LedgerRecognizer, AccountingRuleRecognizer,
)
from modules.recognizers.visual_recognizers import (
    FlowchartRecognizer, GraphRecognizer, CircuitDiagramRecognizer, ConceptTableRecognizer,
    GenericVisualRecognizer, DiagramSubtypeRecognizer, FigureWithCaptionRecognizer,
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
_worked_example = WorkedExampleRecognizer()  # M4.1D

_programming_syntax = ProgrammingSyntaxRecognizer()
_pseudocode = PseudocodeRecognizer()

_journal_format = JournalFormatRecognizer()
_ledger = LedgerRecognizer()
_accounting_rule = AccountingRuleRecognizer()

_flowchart = FlowchartRecognizer()
_graph = GraphRecognizer()
_circuit_diagram = CircuitDiagramRecognizer()
_concept_table = ConceptTableRecognizer()
_diagram_subtype = DiagramSubtypeRecognizer()         # M4.1D
_figure_with_caption = FigureWithCaptionRecognizer()  # M4.1D
_generic_visual = GenericVisualRecognizer()

_definition = DefinitionRecognizer()

# --- Formula Box: reusable formula / identity family --------------------
register(_formula, ["Formula Box", "Worked Example"])
register(_math_identity, ["Formula Box", "Worked Example"])
register(_chemical_reaction, ["Formula Box", "Worked Example"])
register(_economic_identity, ["Formula Box", "Worked Example"])

# --- Worked Example: procedure family ----------------------------------
register(_procedure, ["Worked Example"])
register(_journal_procedure, ["Worked Example"])
register(_worked_example, ["Worked Example"])     # M4.1D
register(_algorithm, ["Worked Example", "Programming Syntax"])

# --- Programming Syntax ------------------------------------------------
register(_programming_syntax, ["Programming Syntax"])
register(_pseudocode, ["Programming Syntax"])

# --- Accounting Format (and accounting-shaped Tables) -------------------
register(_journal_format, ["Accounting Format", "Table"])
register(_ledger, ["Accounting Format", "Table"])
register(_accounting_rule, ["Accounting Format"])

# --- Visual family: Flowchart / Decision Tree / Diagram / Figure / Table
register(_flowchart, ["Flowchart", "Diagram", "Decision Tree"])
register(_graph, ["Figure", "Diagram"])
register(_circuit_diagram, ["Diagram", "Figure"])
register(_diagram_subtype, ["Diagram", "Figure"])         # M4.1D
register(_figure_with_caption, ["Figure"])                 # M4.1D
register(_concept_table, ["Table"])
register(_generic_visual, [
    "Table", "Figure", "Diagram", "Flowchart", "Decision Tree",
    "Programming Syntax", "Accounting Format",
])

# --- Definition ---------------------------------------------------------
register(_definition, ["Definition"])

__all__ = ["register", "candidates_for", "registered_block_types"]
