"""
tests/test_m34_copyright_sanitizer.py — M3.4 unit tests.

Covers:
  - Language detection for every supported code_language value
  - Fallback to "other" for unsupported / unrecognised syntax
  - Pseudocode detection
  - Mixed-syntax snippets (first-match-wins for code_language)
  - Empty / whitespace-only code (None / [] output)
  - All ten code_construct_types individually
  - Constructs absent from a snippet
  - code_construct_types result is sorted and deduplicated
  - Integration: sanitize_educational_objects emits both new fields
  - Backward compatibility: non-programming_syntax objects are unaffected
  - PRESERVE_CODE_SNIPPETS_VERBATIM branch does not emit new fields
  - CODE_LANGUAGE_VOCAB and CODE_CONSTRUCT_VOCAB completeness
  - structural_validator rule 13: valid values pass, unknown values fail
  - structural_validator rule 13: absent / None fields are skipped
  - structural_validator rule 13: wrong-type fields are reported
  - structural_validator STRUCTURAL_VALIDATION_VERSION bumped to 1.1.0
"""
from __future__ import annotations

import sys
import os
import importlib
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path setup — tests live inside the repo; add the repo root to sys.path so
# that `import modules.copyright_sanitizer` etc. work without install.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from modules.copyright_sanitizer import (
    CODE_LANGUAGE_VOCAB,
    CODE_CONSTRUCT_VOCAB,
    _detect_code_language,
    _detect_code_constructs,
    _code_structural_metadata,
    sanitize_educational_objects,
    SanitizeReport,
)
from modules.structural_validator import (
    STRUCTURAL_VALIDATION_VERSION,
    _check_code_vocab_membership,
    validate_structural_completeness,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_prog_obj(code_text: str, source: str = "deterministic") -> Dict[str, Any]:
    """Minimal educational object dict that triggers the programming_syntax branch."""
    return {
        "id": "test-eo-1",
        "educational_object_type": "programming_syntax",
        "source": source,
        "reusable_syntax": code_text,
    }


def _sanitize_one(code_text: str, source: str = "deterministic") -> Dict[str, Any]:
    """Run sanitize_educational_objects on a single object and return the result."""
    report: SanitizeReport = sanitize_educational_objects([_make_prog_obj(code_text, source)])
    assert len(report.sanitized) == 1
    return report.sanitized[0]


def _chapter_with_eo(eo: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal chapter dict wrapping one educational_objects entry."""
    return {"educational_objects": [eo]}


# ===========================================================================
# 1. Closed-vocabulary completeness
# ===========================================================================

class TestClosedVocabularies(unittest.TestCase):

    def test_code_language_vocab_expected_values(self):
        expected = {"python", "c_cpp", "java", "javascript", "sql", "pseudocode", "other"}
        self.assertEqual(CODE_LANGUAGE_VOCAB, expected)

    def test_code_construct_vocab_expected_values(self):
        expected = {
            "loop", "conditional", "function_def", "class_def",
            "import_statement", "assignment", "return_statement",
            "print_statement", "exception_handling", "comment",
        }
        self.assertEqual(CODE_CONSTRUCT_VOCAB, expected)

    def test_vocab_are_frozensets(self):
        self.assertIsInstance(CODE_LANGUAGE_VOCAB, frozenset)
        self.assertIsInstance(CODE_CONSTRUCT_VOCAB, frozenset)


# ===========================================================================
# 2. code_language detection — one test per supported language
# ===========================================================================

class TestCodeLanguageDetection(unittest.TestCase):

    def test_python_def(self):
        self.assertEqual(_detect_code_language("def foo(x):\n    return x"), "python")

    def test_python_import(self):
        self.assertEqual(_detect_code_language("import math\nprint(math.pi)"), "python")

    def test_python_print(self):
        self.assertEqual(_detect_code_language("print('hello')"), "python")

    def test_python_elif(self):
        self.assertEqual(_detect_code_language("if x > 0:\n    pass\nelif x == 0:\n    pass"), "python")

    def test_python_trailing_colon(self):
        self.assertEqual(_detect_code_language("for i in range(10):"), "python")

    def test_c_cpp_include(self):
        self.assertEqual(_detect_code_language("#include <stdio.h>"), "c_cpp")

    def test_c_cpp_void_main(self):
        self.assertEqual(_detect_code_language("void main() { printf('hi'); }"), "c_cpp")

    def test_c_cpp_semicolon(self):
        self.assertEqual(_detect_code_language("int x = 5;"), "c_cpp")

    def test_java_public_static_void(self):
        self.assertEqual(_detect_code_language("public static void main(String[] args) {}"), "java")

    def test_java_public_class(self):
        self.assertEqual(_detect_code_language("public class Foo { }"), "java")

    def test_java_sysout(self):
        self.assertEqual(_detect_code_language("System.out.println('hi');"), "java")

    def test_javascript_function(self):
        self.assertEqual(_detect_code_language("function add(a, b) { return a + b; }"), "javascript")

    def test_javascript_const(self):
        self.assertEqual(_detect_code_language("const x = 5;"), "javascript")

    def test_javascript_consolelog(self):
        self.assertEqual(_detect_code_language("console.log('hi')"), "javascript")

    def test_sql_select(self):
        self.assertEqual(_detect_code_language("SELECT * FROM users WHERE id = 1;"), "sql")

    def test_sql_insert(self):
        self.assertEqual(_detect_code_language("INSERT INTO t VALUES (1, 'a');"), "sql")

    def test_sql_case_insensitive(self):
        self.assertEqual(_detect_code_language("select name from employees"), "sql")

    def test_pseudocode_begin_end(self):
        self.assertEqual(_detect_code_language("Begin\n  Input x\n  Output x*2\nEnd"), "pseudocode")

    def test_pseudocode_procedure(self):
        self.assertEqual(_detect_code_language("Procedure Sort(A)\n  return A\nEnd Procedure"), "pseudocode")

    def test_pseudocode_algorithm(self):
        self.assertEqual(_detect_code_language("Algorithm BubbleSort"), "pseudocode")

    def test_other_fallback(self):
        self.assertEqual(_detect_code_language("x + y = z"), "other")

    def test_other_plain_text(self):
        self.assertEqual(_detect_code_language("This is just plain text."), "other")


# ===========================================================================
# 3. code_language — empty / whitespace input
# ===========================================================================

class TestCodeLanguageEmpty(unittest.TestCase):

    def test_empty_string(self):
        # _detect_code_language gets the raw text; _code_structural_metadata
        # guards the call behind `has_content`.  Test the helper directly too.
        self.assertEqual(_detect_code_language(""), "other")

    def test_whitespace_only(self):
        self.assertEqual(_detect_code_language("   \n  \t  "), "other")

    def test_structural_metadata_empty_returns_none(self):
        result = _code_structural_metadata("")
        self.assertIsNone(result["code_language"])
        self.assertEqual(result["code_construct_types"], [])

    def test_structural_metadata_whitespace_returns_none(self):
        result = _code_structural_metadata("   \n\t  ")
        self.assertIsNone(result["code_language"])
        self.assertEqual(result["code_construct_types"], [])


# ===========================================================================
# 4. Mixed-syntax / priority (first-match-wins for code_language)
# ===========================================================================

class TestCodeLanguagePriority(unittest.TestCase):

    def test_python_beats_pseudocode_when_python_pattern_matches_first(self):
        # A snippet with `def` (Python) AND `begin` (pseudocode) keyword.
        # Python is listed before pseudocode in _CODE_LANGUAGE_PATTERNS.
        snippet = "def foo():\n    begin\n    end"
        self.assertEqual(_detect_code_language(snippet), "python")

    def test_python_beats_c_cpp(self):
        # `def` triggers Python before C/C++ semicolon patterns fire.
        snippet = "def foo(): pass; x = 1;"
        self.assertEqual(_detect_code_language(snippet), "python")

    def test_c_cpp_before_pseudocode(self):
        # `#include` triggers c_cpp before pseudocode keywords.
        snippet = "#include <stdio.h>\nInput x;"
        self.assertEqual(_detect_code_language(snippet), "c_cpp")

    def test_sql_fires_on_keyword_in_prose(self):
        # SQL regex matches word-boundary `SELECT` anywhere — including in prose.
        # This is intentional: the pattern makes a structural observation about
        # keyword presence, not a semantic one about sentence meaning.
        self.assertEqual(_detect_code_language("The SELECT committee met."), "sql")
        self.assertEqual(_detect_code_language("SELECT id FROM table1"), "sql")


# ===========================================================================
# 5. code_construct_types — one test per construct
# ===========================================================================

class TestCodeConstructDetection(unittest.TestCase):

    def _constructs(self, snippet: str) -> List[str]:
        return _detect_code_constructs(snippet)

    def test_loop_for(self):
        self.assertIn("loop", self._constructs("for i in range(10):"))

    def test_loop_while(self):
        self.assertIn("loop", self._constructs("while x > 0: x -= 1"))

    def test_loop_repeat(self):
        self.assertIn("loop", self._constructs("Repeat until done"))

    def test_conditional_if(self):
        self.assertIn("conditional", self._constructs("if x > 0: pass"))

    def test_conditional_else(self):
        self.assertIn("conditional", self._constructs("else: pass"))

    def test_conditional_elif(self):
        self.assertIn("conditional", self._constructs("elif x == 0: pass"))

    def test_conditional_switch(self):
        self.assertIn("conditional", self._constructs("switch(x) { case 1: break; }"))

    def test_function_def_python(self):
        self.assertIn("function_def", self._constructs("def foo(x): return x"))

    def test_function_def_js(self):
        self.assertIn("function_def", self._constructs("function bar() {}"))

    def test_function_def_c(self):
        self.assertIn("function_def", self._constructs("void compute(int x) { }"))

    def test_function_def_pseudocode(self):
        self.assertIn("function_def", self._constructs("Procedure Init(A)"))

    def test_class_def(self):
        self.assertIn("class_def", self._constructs("class Animal: pass"))

    def test_import_python(self):
        self.assertIn("import_statement", self._constructs("import math"))

    def test_import_c(self):
        self.assertIn("import_statement", self._constructs("#include <stdio.h>"))

    def test_assignment(self):
        self.assertIn("assignment", self._constructs("x = 5"))

    def test_assignment_not_equality(self):
        # `==` should NOT trigger assignment
        self.assertNotIn("assignment", self._constructs("if x == 5: pass"))

    def test_return_statement(self):
        self.assertIn("return_statement", self._constructs("return x + 1"))

    def test_print_python(self):
        self.assertIn("print_statement", self._constructs("print(x)"))

    def test_print_c(self):
        self.assertIn("print_statement", self._constructs("printf('%d', x);"))

    def test_print_java(self):
        self.assertIn("print_statement", self._constructs("System.out.println(x);"))

    def test_print_js(self):
        self.assertIn("print_statement", self._constructs("console.log(x)"))

    def test_exception_try_except(self):
        self.assertIn("exception_handling", self._constructs("try:\n    pass\nexcept Exception:\n    pass"))

    def test_exception_throw(self):
        self.assertIn("exception_handling", self._constructs("throw new Error()"))

    def test_exception_raise(self):
        self.assertIn("exception_handling", self._constructs("raise ValueError('bad')"))

    def test_comment_hash(self):
        self.assertIn("comment", self._constructs("# This is a comment"))

    def test_comment_double_slash(self):
        self.assertIn("comment", self._constructs("// C-style comment"))

    def test_comment_block(self):
        self.assertIn("comment", self._constructs("/* block comment */"))

    def test_no_constructs_plain(self):
        # A snippet with no matching constructs returns an empty list.
        self.assertEqual(self._constructs("x + y"), [])

    def test_result_is_sorted(self):
        snippet = "for i in range(10):\n    if i > 0:\n        print(i)"
        result = self._constructs(snippet)
        self.assertEqual(result, sorted(result))

    def test_result_has_no_duplicates(self):
        # Multiple `if` statements should still yield "conditional" once.
        snippet = "if a: pass\nif b: pass\nif c: pass"
        constructs = self._constructs(snippet)
        self.assertEqual(len(constructs), len(set(constructs)))

    def test_multiple_constructs_detected(self):
        snippet = (
            "def process(items):\n"
            "    for item in items:\n"
            "        if item > 0:\n"
            "            print(item)\n"
            "    return True\n"
        )
        result = self._constructs(snippet)
        self.assertIn("function_def", result)
        self.assertIn("loop", result)
        self.assertIn("conditional", result)
        self.assertIn("print_statement", result)
        self.assertIn("return_statement", result)


# ===========================================================================
# 6. _code_structural_metadata — integration of all four fields
# ===========================================================================

class TestCodeStructuralMetadata(unittest.TestCase):

    def test_existing_fields_unchanged(self):
        result = _code_structural_metadata("def foo(): pass")
        self.assertEqual(result["code_line_count"], 1)
        self.assertTrue(result["has_code_content"])

    def test_new_fields_present(self):
        result = _code_structural_metadata("def foo(): pass")
        self.assertIn("code_language", result)
        self.assertIn("code_construct_types", result)

    def test_python_snippet_full(self):
        snippet = "def add(a, b):\n    return a + b"
        result = _code_structural_metadata(snippet)
        self.assertEqual(result["code_language"], "python")
        self.assertIn("function_def", result["code_construct_types"])
        self.assertIn("return_statement", result["code_construct_types"])
        self.assertEqual(result["code_line_count"], 2)
        self.assertTrue(result["has_code_content"])

    def test_empty_code_none_language(self):
        result = _code_structural_metadata("")
        self.assertIsNone(result["code_language"])
        self.assertEqual(result["code_construct_types"], [])
        self.assertEqual(result["code_line_count"], 0)
        self.assertFalse(result["has_code_content"])

    def test_whitespace_only_none_language(self):
        result = _code_structural_metadata("   \n\n\t\n  ")
        self.assertIsNone(result["code_language"])
        self.assertEqual(result["code_construct_types"], [])

    def test_other_language_no_constructs(self):
        result = _code_structural_metadata("a + b + c")
        self.assertEqual(result["code_language"], "other")
        self.assertEqual(result["code_construct_types"], [])


# ===========================================================================
# 7. sanitize_educational_objects integration
# ===========================================================================

class TestSanitizeEducationalObjectsIntegration(unittest.TestCase):

    def test_python_object_gets_both_new_fields(self):
        result = _sanitize_one("def greet(name):\n    print('hello', name)")
        self.assertIn("code_language", result)
        self.assertIn("code_construct_types", result)
        self.assertEqual(result["code_language"], "python")
        self.assertIn("function_def", result["code_construct_types"])
        self.assertIn("print_statement", result["code_construct_types"])

    def test_existing_fields_still_emitted(self):
        result = _sanitize_one("def foo(): pass")
        self.assertIn("code_line_count", result)
        self.assertIn("has_code_content", result)

    def test_empty_code_new_fields_are_none_and_empty(self):
        # An object with an empty reusable_syntax string
        result = _sanitize_one("")
        self.assertIsNone(result["code_language"])
        self.assertEqual(result["code_construct_types"], [])

    def test_c_snippet(self):
        result = _sanitize_one("#include <stdio.h>\nvoid main() { printf('hi'); }")
        self.assertEqual(result["code_language"], "c_cpp")
        self.assertIn("function_def", result["code_construct_types"])
        self.assertIn("import_statement", result["code_construct_types"])
        self.assertIn("print_statement", result["code_construct_types"])

    def test_sql_snippet(self):
        result = _sanitize_one("SELECT name FROM students WHERE grade > 90;")
        self.assertEqual(result["code_language"], "sql")

    def test_pseudocode_snippet(self):
        result = _sanitize_one("Begin\n  Input n\n  Output n*2\nEnd")
        self.assertEqual(result["code_language"], "pseudocode")

    def test_other_language_snippet(self):
        result = _sanitize_one("x = f(x) + g(y)")
        self.assertEqual(result["code_language"], "other")

    def test_reusable_syntax_stripped_from_production(self):
        # When PRESERVE_CODE_SNIPPETS_VERBATIM is False (default), the raw
        # syntax text must not appear in the sanitized record.
        with patch("config.PRESERVE_CODE_SNIPPETS_VERBATIM", False):
            result = _sanitize_one("def secret(): pass")
        self.assertNotIn("reusable_syntax", result)

    def test_reusable_syntax_kept_when_preserve_flag_true(self):
        # When PRESERVE_CODE_SNIPPETS_VERBATIM is True, the raw text is kept
        # and the new structural fields are NOT emitted (the flag-guarded
        # branch returns early before calling _code_structural_metadata).
        with patch("config.PRESERVE_CODE_SNIPPETS_VERBATIM", True):
            obj = _make_prog_obj("def foo(): pass")
            report = sanitize_educational_objects([obj])
            result = report.sanitized[0]
        self.assertIn("reusable_syntax", result)
        # new fields should NOT be present when the verbatim flag is set
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)


# ===========================================================================
# 8. Backward compatibility — non-programming_syntax objects untouched
# ===========================================================================

class TestBackwardCompatibility(unittest.TestCase):

    def _sanitize_non_prog(self, obj_type: str, extra: Dict = None) -> Dict[str, Any]:
        obj = {"id": "x", "educational_object_type": obj_type, "source": "deterministic"}
        if extra:
            obj.update(extra)
        report = sanitize_educational_objects([obj])
        return report.sanitized[0]

    def test_concept_object_no_new_fields(self):
        result = self._sanitize_non_prog("concept")
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)

    def test_formula_or_procedure_no_new_fields(self):
        result = self._sanitize_non_prog("formula_or_procedure",
                                         extra={"procedure_steps": ["Step 1: do X"]})
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)

    def test_accounting_format_no_new_fields(self):
        result = self._sanitize_non_prog("accounting_format",
                                         extra={"format_type": "accounting_rule",
                                                "rules": ["Debit the receiver"]})
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)

    def test_vlm_sourced_programming_syntax_not_affected(self):
        # source == "vlm_fallback" objects must pass through without sanitization.
        obj = {
            "id": "vlm-eo",
            "educational_object_type": "programming_syntax",
            "source": "vlm_fallback",
            "reusable_syntax": "def foo(): pass",
        }
        report = sanitize_educational_objects([obj])
        result = report.sanitized[0]
        # reusable_syntax should be untouched
        self.assertIn("reusable_syntax", result)
        # new fields should NOT be added (sanitizer skips vlm_fallback objects)
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)

    def test_empty_object_list_returns_empty(self):
        report = sanitize_educational_objects([])
        self.assertEqual(report.sanitized, [])
        self.assertEqual(report.debug_entries, [])

    def test_list_object_no_new_fields(self):
        # A figure (visual) object must not receive code fields.
        obj = {"id": "fig-1", "educational_object_type": "figure", "source": "deterministic"}
        report = sanitize_educational_objects([obj])
        result = report.sanitized[0]
        self.assertNotIn("code_language", result)
        self.assertNotIn("code_construct_types", result)


# ===========================================================================
# 9. Structural validator — rule 13 (_check_code_vocab_membership)
# ===========================================================================

class TestValidatorCodeVocabMembership(unittest.TestCase):

    def _issues(self, eo: Dict[str, Any]) -> List[Dict[str, Any]]:
        return _check_code_vocab_membership(_chapter_with_eo(eo))

    # --- valid values pass ---

    def test_valid_language_no_issues(self):
        for lang in CODE_LANGUAGE_VOCAB:
            with self.subTest(lang=lang):
                eo = {"id": f"eo-{lang}", "code_language": lang}
                self.assertEqual(self._issues(eo), [])

    def test_valid_construct_no_issues(self):
        eo = {"id": "eo-1", "code_construct_types": sorted(CODE_CONSTRUCT_VOCAB)}
        self.assertEqual(self._issues(eo), [])

    def test_absent_code_language_no_issues(self):
        eo = {"id": "eo-1", "code_construct_types": ["loop"]}
        self.assertEqual(self._issues(eo), [])

    def test_none_code_language_no_issues(self):
        eo = {"id": "eo-1", "code_language": None}
        self.assertEqual(self._issues(eo), [])

    def test_absent_code_construct_types_no_issues(self):
        eo = {"id": "eo-1", "code_language": "python"}
        self.assertEqual(self._issues(eo), [])

    def test_empty_code_construct_types_no_issues(self):
        eo = {"id": "eo-1", "code_construct_types": []}
        self.assertEqual(self._issues(eo), [])

    def test_no_code_fields_at_all_no_issues(self):
        eo = {"id": "eo-1", "educational_object_type": "concept"}
        self.assertEqual(self._issues(eo), [])

    # --- unknown values are reported ---

    def test_unknown_language_is_error(self):
        eo = {"id": "eo-bad-lang", "code_language": "ruby"}
        issues = self._issues(eo)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "ERROR")
        self.assertEqual(issues[0]["rule"], "code_language_unknown_value")
        self.assertEqual(issues[0]["details"]["value"], "ruby")

    def test_unknown_construct_is_warning(self):
        eo = {"id": "eo-bad-construct", "code_construct_types": ["loop", "magic_construct"]}
        issues = self._issues(eo)
        # "loop" is valid; "magic_construct" triggers WARNING
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "WARNING")
        self.assertEqual(issues[0]["rule"], "code_construct_types_unknown_value")
        self.assertEqual(issues[0]["details"]["value"], "magic_construct")

    def test_multiple_unknown_constructs_all_reported(self):
        eo = {"id": "eo-multi", "code_construct_types": ["bad1", "bad2", "loop"]}
        issues = self._issues(eo)
        rules = [i["rule"] for i in issues]
        self.assertEqual(rules.count("code_construct_types_unknown_value"), 2)

    # --- wrong types ---

    def test_code_language_wrong_type_is_error(self):
        eo = {"id": "eo-wrong-type", "code_language": 42}
        issues = self._issues(eo)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "ERROR")
        self.assertEqual(issues[0]["rule"], "code_language_wrong_type")

    def test_code_construct_types_wrong_type_is_error(self):
        eo = {"id": "eo-not-list", "code_construct_types": "loop"}
        issues = self._issues(eo)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "ERROR")
        self.assertEqual(issues[0]["rule"], "code_construct_types_wrong_type")

    def test_code_construct_types_non_string_entry_is_warning(self):
        eo = {"id": "eo-non-str", "code_construct_types": ["loop", 99]}
        issues = self._issues(eo)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "WARNING")
        self.assertEqual(issues[0]["rule"], "code_construct_types_non_string_entry")

    # --- non-dict entries in educational_objects are skipped ---

    def test_non_dict_entries_skipped(self):
        chapter = {"educational_objects": [None, "bad", {"id": "x", "code_language": "python"}]}
        issues = _check_code_vocab_membership(chapter)
        self.assertEqual(issues, [])

    # --- object_id is recorded in the issue ---

    def test_issue_carries_object_id(self):
        eo = {"id": "my-eo-id", "code_language": "haskell"}
        issues = self._issues(eo)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["object_id"], "my-eo-id")

    # --- empty / missing educational_objects section ---

    def test_missing_section_no_issues(self):
        issues = _check_code_vocab_membership({})
        self.assertEqual(issues, [])

    def test_empty_section_no_issues(self):
        issues = _check_code_vocab_membership({"educational_objects": []})
        self.assertEqual(issues, [])


# ===========================================================================
# 10. Structural validator version bump
# ===========================================================================

class TestValidatorVersion(unittest.TestCase):

    def test_version_is_1_1_0(self):
        self.assertEqual(STRUCTURAL_VALIDATION_VERSION, "1.1.0")

    def test_rule_name_in_report_on_valid_chapter(self):
        # A minimal but technically valid chapter that passes all rules
        # (many checks require sections that aren't present — the validator
        # does not crash on them).  We just need `code_vocab_membership` to
        # appear in `rules_run`.
        chapter = {"educational_objects": []}
        report = validate_structural_completeness(chapter)
        self.assertIn("code_vocab_membership", report["rules_run"])


# ===========================================================================
# 11. End-to-end: sanitize → validate round-trip
# ===========================================================================

class TestEndToEndRoundTrip(unittest.TestCase):

    def test_sanitized_python_object_passes_vocab_check(self):
        snippet = (
            "def bubble_sort(arr):\n"
            "    for i in range(len(arr)):\n"
            "        for j in range(len(arr)-1):\n"
            "            if arr[j] > arr[j+1]:\n"
            "                arr[j], arr[j+1] = arr[j+1], arr[j]\n"
            "    return arr\n"
        )
        sanitized = _sanitize_one(snippet)
        issues = _check_code_vocab_membership({"educational_objects": [sanitized]})
        self.assertEqual(issues, [],
                         msg=f"Unexpected issues: {issues}")

    def test_sanitized_sql_object_passes_vocab_check(self):
        snippet = "SELECT e.name, d.name FROM employees e JOIN departments d ON e.dept_id = d.id;"
        sanitized = _sanitize_one(snippet)
        issues = _check_code_vocab_membership({"educational_objects": [sanitized]})
        self.assertEqual(issues, [])

    def test_sanitized_empty_code_passes_vocab_check(self):
        sanitized = _sanitize_one("")
        issues = _check_code_vocab_membership({"educational_objects": [sanitized]})
        self.assertEqual(issues, [])

    def test_sanitized_pseudocode_passes_vocab_check(self):
        snippet = "Algorithm MergeSort(A, left, right):\n  if left < right:\n    mid = (left+right)//2\n    MergeSort(A, left, mid)\n    MergeSort(A, mid+1, right)\n"
        sanitized = _sanitize_one(snippet)
        issues = _check_code_vocab_membership({"educational_objects": [sanitized]})
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
