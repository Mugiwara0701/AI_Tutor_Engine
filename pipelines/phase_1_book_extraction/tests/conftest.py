"""
tests/conftest.py — shared fixtures for the M6.1 TKB test suite.

Provides deterministic test data that exercises the full pipeline
without requiring a live compiler run. All fixtures produce
stable, repeatable data.
"""
import sys
import os
import pytest

# Ensure the project root is on the path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Concept fixtures
# ---------------------------------------------------------------------------

def make_concept(concept_id: str, name: str, chapter: str, **kwargs) -> dict:
    return {
        "id": concept_id,
        "concept_id": concept_id,
        "name": name,
        "chapter_id": chapter,
        "chapter": chapter,
        "description": f"Description of {name}",
        "bloom_level": kwargs.get("bloom_level", "understand"),
        "difficulty": kwargs.get("difficulty", "medium"),
        "prerequisites": kwargs.get("prerequisites", []),
        **{k: v for k, v in kwargs.items()
           if k not in ("bloom_level", "difficulty", "prerequisites")},
    }


@pytest.fixture
def two_chapter_concepts():
    """12 concepts across 2 chapters — exercises multi-chapter pipeline."""
    return [
        make_concept("c1", "Motion", "ch1", prerequisites=[], bloom_level="remember", difficulty="easy"),
        make_concept("c2", "Velocity", "ch1", prerequisites=["c1"], bloom_level="understand", difficulty="easy"),
        make_concept("c3", "Acceleration", "ch1", prerequisites=["c2"], bloom_level="apply", difficulty="medium"),
        make_concept("c4", "Force", "ch1", prerequisites=["c3"], bloom_level="apply", difficulty="medium"),
        make_concept("c5", "Newton 1st", "ch1", prerequisites=["c1"], bloom_level="understand", difficulty="easy"),
        make_concept("c6", "Newton 2nd", "ch1", prerequisites=["c4", "c5"], bloom_level="apply", difficulty="hard"),
        make_concept("c7", "Energy", "ch2", prerequisites=["c6"], bloom_level="understand", difficulty="medium"),
        make_concept("c8", "Work", "ch2", prerequisites=["c4"], bloom_level="apply", difficulty="medium"),
        make_concept("c9", "Power", "ch2", prerequisites=["c8"], bloom_level="apply", difficulty="medium"),
        make_concept("c10", "Potential Energy", "ch2", prerequisites=["c7"], bloom_level="analyze", difficulty="hard"),
        make_concept("c11", "Kinetic Energy", "ch2", prerequisites=["c7"], bloom_level="analyze", difficulty="hard"),
        make_concept("c12", "Conservation", "ch2", prerequisites=["c10", "c11"], bloom_level="evaluate", difficulty="hard"),
    ]


@pytest.fixture
def minimal_knowledge_graph(two_chapter_concepts):
    """Minimal KnowledgeGraph dict from concept fixtures."""
    edges = []
    for c in two_chapter_concepts:
        for prereq in c.get("prerequisites", []):
            edges.append({
                "source": prereq,
                "target": c["id"],
                "type": "prerequisite",
                "relationship_type": "prerequisite",
            })
    return {
        "nodes": two_chapter_concepts,
        "edges": edges,
        "schema_version": "test",
    }


@pytest.fixture
def minimal_dst(two_chapter_concepts):
    """Minimal DocumentStructureTree from concepts."""
    from collections import defaultdict
    chapters = defaultdict(list)
    for c in two_chapter_concepts:
        chapters[c["chapter_id"]].append(c["id"])
    nodes = []
    for i, (ch_id, concept_ids) in enumerate(sorted(chapters.items())):
        nodes.append({
            "id": ch_id,
            "chapter_number": i + 1,
            "title": f"Chapter {i + 1}",
            "type": "chapter",
            "position_index": i,
            "concept_ids": concept_ids,
        })
    return {"nodes": nodes}


@pytest.fixture
def minimal_compiler_artifacts(minimal_knowledge_graph, minimal_dst, two_chapter_concepts):
    """Minimal compiler artifacts dict — the minimum needed for a full TKB build."""
    return {
        "knowledge_graph": minimal_knowledge_graph,
        "document_structure_tree": minimal_dst,
        "optimized_knowledge_package": {
            "concepts": two_chapter_concepts,
            "chapter_ids": ["ch1", "ch2"],
            "artifact_id": "test-okp-001",
        },
    }


@pytest.fixture
def test_config():
    """Standard test config — no strict validation so tests surface all issues."""
    return {
        "strict_validation": False,
        "enforce_determinism": True,
        "source_artifact_id": "test-build-001",
        "pipeline_version": "M6.1.0-test",
        "chapter_ids": ["ch1", "ch2"],
    }
