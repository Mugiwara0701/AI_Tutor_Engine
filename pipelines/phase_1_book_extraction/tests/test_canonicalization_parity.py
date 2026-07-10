"""
tests/test_canonicalization_parity.py — parity tests for the
canonicalization.py consolidation.

SCOPE: these are NOT a re-test of fingerprint generation, determinism
validation, or any other behavior already covered by tests/
test_fingerprints.py, tests/test_c4_2_fingerprints_readiness.py, or
tests/test_d2_determinism.py. Those suites already prove each module's
own fingerprints/determinism checks behave correctly; this file proves
one narrower thing those suites don't: that compiler/fingerprints.py,
knowledge_graph/fingerprints.py, and validation/determinism.py all
canonicalize the same input the same way, because all three now import
the exact same implementation (canonicalization.py) rather than
maintaining three independently-hand-rolled copies.

Before this consolidation these three were three separate functions
that happened to behave identically; nothing enforced that they'd stay
that way. These tests exist so that if a future change updates one
call site's canonicalization behavior without updating the others, a
test fails immediately here -- instead of three fingerprint algorithms
silently drifting apart.
"""
from __future__ import annotations

import canonicalization
import compiler.fingerprints as compiler_fingerprints
import knowledge_graph.fingerprints as graph_fingerprints
import validation.determinism as determinism


# --------------------------------------------------------------------------
# Shared fixtures: representative payloads exercising nesting, lists,
# volatile keys at multiple depths, and non-JSON-native values (so
# `default=str` gets exercised too).
# --------------------------------------------------------------------------

def _sample_payloads():
    return [
        {},
        {"a": 1, "b": 2, "c": 3},
        {"generated_at": "2026-01-01T00:00:00+00:00", "node_count": 4},
        {
            "outer": {
                "inner": {"created_at": "x", "value": 1},
                "list": [
                    {"resolved_at": "y", "id": "n1"},
                    {"id": "n2", "timestamp": "z"},
                ],
            },
            "approx_memory_bytes": 12345,
        },
        [1, 2, {"enriched_at": "w", "keep": True}],
        {"nested_none": None, "flag": False, "count": 0},
    ]


# --------------------------------------------------------------------------
# Task 5: single-source-of-truth check -- all three modules' locally
# bound names are literally the same function objects imported from
# canonicalization.py, not three separately-defined functions that
# happen to agree today.
# --------------------------------------------------------------------------

def test_all_three_modules_share_the_same_function_objects():
    assert compiler_fingerprints.VOLATILE_KEYS is canonicalization.VOLATILE_KEYS
    assert graph_fingerprints.VOLATILE_KEYS is canonicalization.VOLATILE_KEYS
    assert determinism.VOLATILE_KEYS is canonicalization.VOLATILE_KEYS

    assert compiler_fingerprints._canonical_json is canonicalization.canonical_json
    assert graph_fingerprints._canonical_json is canonicalization.canonical_json
    assert determinism._canonical_json is canonicalization.canonical_json

    assert compiler_fingerprints._strip_volatile is canonicalization.strip_volatile
    assert graph_fingerprints._strip_volatile is canonicalization.strip_volatile
    assert determinism._strip_volatile is canonicalization.strip_volatile

    assert compiler_fingerprints._sha256_hexdigest is canonicalization.sha256_hexdigest
    assert graph_fingerprints._sha256_hexdigest is canonicalization.sha256_hexdigest


# --------------------------------------------------------------------------
# Task 5: behavioral parity -- even without the identity check above,
# all three modules' canonicalization of the same input must be
# byte-identical.
# --------------------------------------------------------------------------

def test_canonical_json_identical_across_all_three_modules():
    for payload in _sample_payloads():
        compiler_out = compiler_fingerprints._canonical_json(payload)
        graph_out = graph_fingerprints._canonical_json(payload)
        determinism_out = determinism._canonical_json(payload)
        shared_out = canonicalization.canonical_json(payload)

        assert compiler_out == graph_out == determinism_out == shared_out


def test_strip_volatile_identical_across_all_three_modules():
    for payload in _sample_payloads():
        compiler_out = compiler_fingerprints._strip_volatile(payload)
        graph_out = graph_fingerprints._strip_volatile(payload)
        determinism_out = determinism._strip_volatile(payload)
        shared_out = canonicalization.strip_volatile(payload)

        assert compiler_out == graph_out == determinism_out == shared_out


def test_sha256_hexdigest_identical_between_compiler_and_graph_modules():
    # validation/determinism.py never hashes (it only compares canonical
    # text), so only the two fingerprint-generating modules are checked
    # here.
    for text in ("", "x", '{"a":1,"b":2}', "unicode-\u00e9-check"):
        compiler_out = compiler_fingerprints._sha256_hexdigest(text)
        graph_out = graph_fingerprints._sha256_hexdigest(text)
        shared_out = canonicalization.sha256_hexdigest(text)

        assert compiler_out == graph_out == shared_out
        assert len(compiler_out) == 64  # sanity: real SHA-256 hex digest


# --------------------------------------------------------------------------
# Task 5: VOLATILE_KEYS single-source-of-truth -- the set itself must be
# the exact same object everywhere, not three copies that happen to
# have the same members today.
# --------------------------------------------------------------------------

def test_volatile_keys_is_a_single_shared_constant():
    assert canonicalization.VOLATILE_KEYS == frozenset({
        "generated_at",
        "enriched_at",
        "normalized_at",
        "resolved_at",
        "created_at",
        "timestamp",
        "approx_memory_bytes",
    })
    # Re-exported under its original name for backward compatibility --
    # `from compiler.fingerprints import VOLATILE_KEYS` (used elsewhere
    # in this codebase, e.g. tests/test_fingerprints.py) must still work.
    assert compiler_fingerprints.VOLATILE_KEYS == canonicalization.VOLATILE_KEYS


# --------------------------------------------------------------------------
# Task 6 (regression safety, narrow slice): the shared module's output
# for a fixed, hand-computed input must match a hand-verified expected
# digest -- guards against the consolidation itself silently changing
# the canonicalization algorithm.
# --------------------------------------------------------------------------

def test_canonical_json_output_matches_known_expected_text():
    payload = {"b": 2, "a": 1, "generated_at": "should-be-stripped"}
    assert canonicalization.canonical_json(payload) == '{"a":1,"b":2}'


def test_canonical_json_is_key_order_independent():
    payload_1 = {"a": 1, "b": {"x": 1, "y": 2}}
    payload_2 = {"b": {"y": 2, "x": 1}, "a": 1}
    assert canonicalization.canonical_json(payload_1) == canonicalization.canonical_json(payload_2)


def test_strip_volatile_does_not_mutate_input():
    payload = {"generated_at": "t", "nested": {"created_at": "t2", "keep": 1}}
    original = {"generated_at": "t", "nested": {"created_at": "t2", "keep": 1}}
    canonicalization.strip_volatile(payload)
    assert payload == original