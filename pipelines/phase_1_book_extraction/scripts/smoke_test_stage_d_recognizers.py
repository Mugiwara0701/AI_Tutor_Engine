"""
Manual smoke test for the Stage D recognizer framework. Builds fake
Block objects directly (no PDF, no VLM) and runs them through
stage_d_extraction.extract_educational_objects(use_vlm=False) to check
that each recognizer family routes to the right educational_object_type
with a sensible confidence, and that nothing regresses for the
pre-existing Formula Box / Worked Example / Definition / Table paths.

Run with: python3 scripts/smoke_test_stage_d_recognizers.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.stage_a_geometry import Block
from modules.pdf_parser import Line
from modules import stage_d_extraction


def _line(text):
    return Line(text=text, size=10.0, max_size=10.0, bold=False, font="x", page=0, y=0.0, page_height=800.0)


def _block(block_id, block_type, texts, grouping_meta=None, priority="high"):
    b = Block(
        block_id=block_id, page=0, bbox=(0, 0, 100, 20),
        lines=[_line(t) for t in texts],
        grouping_meta=grouping_meta or {},
    )
    b.block_type = block_type
    b.priority = priority
    b.confidence = 0.7
    return b


cases = [
    # Formula Box family
    _block("b1", "Formula Box", ["F = m * a"]),
    _block("b2", "Formula Box", ["sin^2(x) + cos^2(x) = 1"]),
    _block("b3", "Formula Box", ["NaCl + AgNO3 -> AgCl + NaNO3"]),
    _block("b4", "Formula Box", ["GDP = C + I + G + X - M"]),
    # Worked Example: procedure + numeric substitution
    _block("b5", "Worked Example", [
        "Step 1: Identify the known values",
        "Step 2: Apply the formula v = u + a * t",
        "= 5 + 2 * 3",
        "= 11",
    ]),
    # Programming Syntax
    _block("b6", "Programming Syntax", ["def add(a, b):", "    return a + b"]),
    _block("b7", "Programming Syntax", ["BEGIN", "INPUT n", "OUTPUT n * 2", "END"]),
    # Accounting Format
    _block("b8", "Accounting Format", ["Date Particulars L.F. Debit Credit"]),
    _block("b9", "Accounting Format", ["Debit the receiver, Credit the giver"]),
    # Table -> concept table vs generic
    _block("b10", "Table", ["Difference between Physical and Chemical change"],
           grouping_meta={"caption": "Comparison of Physical and Chemical changes"}),
    _block("b11", "Table", ["Random data table"], grouping_meta={"caption": "Population by year"}),
    # Diagram family
    _block("b12", "Diagram", [""], grouping_meta={"caption": "Circuit diagram showing a resistor and battery"}),
    _block("b13", "Diagram", [""], grouping_meta={"caption": "Flowchart of the water cycle"}),
    _block("b14", "Figure", [""], grouping_meta={"caption": "Graph of velocity vs time"}),
    # Definition (unchanged path)
    _block("b15", "Definition", ["photosynthesis"], grouping_meta={"candidate_term": "Photosynthesis"}),
]

objs = stage_d_extraction.extract_educational_objects(cases, doc=None, use_vlm=False)

for o in objs:
    print(f"{o['block_id']:>4} | type={o['block_type']:<18} -> "
          f"eo_type={o['educational_object_type']:<20} "
          f"recognizer={o.get('recognizer', '-'):<16} "
          f"confidence={o['confidence']:.2f} "
          f"source={o.get('source')}")
