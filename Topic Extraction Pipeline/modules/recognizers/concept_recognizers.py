"""
modules/recognizers/concept_recognizers.py — the candidate recognizer for
"Definition" blocks.

Ported unchanged from the pre-modular `_extract_definition`: extracts the
term + location only, never the definition text itself. Ported into the
registry framework mainly for consistency (every Stage B block_type now
goes through the same dispatch path in stage_d_extraction), and so a
future second concept-style recognizer (e.g. a glossary-entry recognizer)
can be added the same way as every other recognizer in this package.
Never had a VLM path before and still doesn't (`Recognizer.vlm_fallback`'s
default of None is kept as-is).
"""
from typing import Optional

from modules.stage_a_geometry import Block
from modules.recognizers.base import Recognizer, RecognitionResult


class DefinitionRecognizer(Recognizer):
    name = "definition"
    educational_object_type = "concept"

    def recognize(self, block: Block) -> Optional[RecognitionResult]:
        term = (block.grouping_meta or {}).get("candidate_term", "")
        return RecognitionResult(
            confidence=0.75,
            data={"term": term},
            educational_object_type=self.educational_object_type,
            recognizer_name=self.name,
        )
