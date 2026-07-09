"""
graph_builder.py — derives the three "graph"-shaped sections of the schema
(learning_graph, concept_graph, semantic_index) purely from the structured
records already produced by pdf_parser + semantic_processor. No VLM calls
here — this is graph assembly over data we already have.

ARCHITECTURAL NOTE (hardening-pass correction): an earlier revision of this
docstring claimed pipeline.py "no longer calls this module" and that graph
assembly was Phase 2's job. That was aspirational, not actual: pipeline.py
DOES call build_learning_graph/build_concept_graph/build_semantic_index for
every chapter and writes their output into the Chapter JSON it produces
(see schemas/educational_objects_schema.py's docstring and
modules/validator.py's validate_educational_objects_document for the other
half of that same stale claim). Per the current task framing, Phase 1 IS
the compiler-grade Knowledge Graph generator and IS the single source of
truth for downstream phases, so these derived graph sections belong here.
This module's actual, current status: load-bearing and in active use.

Heuristics used:
  - learning_graph edges: topic[i] -> topic[i+1] in reading order (a
    "covered before" prerequisite chain), plus any explicit `prerequisites`
    the VLM attached to a topic.
  - concept_graph edges: two concepts are linked if they co-occur in the
    same topic, or if the VLM listed one as a `related_concepts` of another.
  - semantic_index: a reverse lookup, concept -> topics/definitions/figures/
    tables/equations that reference it (matched by concept name appearing
    in each record's `concepts` list or by simple substring match against
    definition terms / figure & table concept lists).
"""
from typing import List, Dict, Any
from collections import defaultdict


def build_learning_graph(topics: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = [t["id"] for t in topics]
    edges = []
    ordered = sorted(topics, key=lambda t: t.get("reading_order", 0))
    for i in range(len(ordered) - 1):
        edges.append({"source": ordered[i]["id"], "target": ordered[i + 1]["id"],
                       "relationship_type": "precedes", "weight": 1.0})
    for t in topics:
        for prereq_title in t.get("prerequisites", []) or []:
            match = next((o for o in topics if o["title"].lower() == str(prereq_title).lower()), None)
            if match:
                edges.append({"source": match["id"], "target": t["id"],
                              "relationship_type": "prerequisite_of", "weight": 1.0})
    return {"nodes": nodes, "edges": edges}


def build_concept_graph(concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = [c["id"] for c in concepts]
    by_topic = defaultdict(list)
    for c in concepts:
        # A canonical concept can now belong to several topics (see
        # pipeline.py's concept_registry dedup) -- fan it out to every one
        # of them, not just the first, otherwise co-occurrence edges would
        # be missed for topics 2..n.
        topic_ids = c.get("topics") or ([c["topic"]] if c.get("topic") else [])
        for topic_id in topic_ids:
            by_topic[topic_id].append(c["id"])

    edges = []
    seen = set()
    for topic, ids in by_topic.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair = tuple(sorted((ids[i], ids[j])))
                if pair not in seen:
                    seen.add(pair)
                    edges.append({"source": pair[0], "target": pair[1],
                                  "relationship_type": "co_occurs_in_topic", "weight": 0.6})

    name_to_id = {c["name"].lower(): c["id"] for c in concepts}
    for c in concepts:
        for rel in c.get("related_concepts", []) or []:
            target_id = name_to_id.get(str(rel).lower())
            if target_id and target_id != c["id"]:
                pair = tuple(sorted((c["id"], target_id)))
                if pair not in seen:
                    seen.add(pair)
                    edges.append({"source": pair[0], "target": pair[1],
                                  "relationship_type": "related_to", "weight": 1.0})
    return {"nodes": nodes, "edges": edges}


def build_semantic_index(concepts: List[Dict[str, Any]], topics: List[Dict[str, Any]],
                          definitions: List[Dict[str, Any]], figures: List[Dict[str, Any]],
                          tables: List[Dict[str, Any]], equations: List[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    index = []
    for c in concepts:
        name_lower = c["name"].lower()
        # A4: topics/figures/tables now carry canonical concept_ids (see
        # pipeline.py + schemas/chapter_schema.py) rather than concept
        # names in their `concepts` field, so matching is an exact id
        # membership check, not a name/substring heuristic, for the
        # objects that have adopted the canonical reference. The topic
        # title substring check and the definition/equation text-search
        # heuristics are unaffected -- those never held concept names to
        # begin with.
        matched_topics = [t["id"] for t in topics if c["id"] in t.get("concepts", [])
                           or name_lower in t.get("title", "").lower()]
        matched_defs = [d["term"] for d in definitions if name_lower in d["term"].lower()
                         or d["term"].lower() in name_lower]
        matched_figs = [f["id"] for f in figures if c["id"] in f.get("concept_ids", [])]
        matched_tabs = [t["id"] for t in tables if c["id"] in t.get("concept_ids", [])]
        matched_eqs = [e["id"] for e in equations if name_lower in e.get("semantic_meaning", "").lower()]
        index.append({
            "concept": c["name"],
            "topics": matched_topics,
            "definitions": matched_defs,
            "figures": matched_figs,
            "tables": matched_tabs,
            "equations": matched_eqs,
        })
    return index
