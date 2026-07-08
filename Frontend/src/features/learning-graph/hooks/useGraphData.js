// src/features/learning-graph/hooks/useGraphData.js
// Placeholder for useGraphData — implement component/logic here.

// src/features/learning-graph/hooks/useGraphData.js

import { useMemo, useState } from "react";
import mockGraph from "../data/mockGraph.json";
import {
  buildEdges,
  buildOverviewEdges,
} from "../components/edges/customEdges.js";

const NODE_COLORS = {
  mainTopic: "#22C55E",
  subTopic: "#2563EB",
  concept: "#A855F7",
};

function getMasteryColor(mastery) {
  if (mastery >= 80) return "bg-green-500";
  if (mastery >= 60) return "bg-yellow-500";
  if (mastery >= 40) return "bg-orange-500";
  return "bg-red-500";
}

export function useGraphData() {
  const [filters, setFilters] = useState({
    classValue: "",
    subjectValue: "",
    bookValue: "",
    chapterValue: "",
  });
  const [showMastery, setShowMastery] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState(
    () =>
      mockGraph.nodes.find((n) => n.type === "mainTopic")?.id ??
      mockGraph.nodes[0]?.id ??
      null,
  );

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  // Full interactive nodes for the main canvas.
  const nodes = useMemo(
    () =>
      mockGraph.nodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: {
          label: node.label,
          showMastery,
          masteryColor: getMasteryColor(node.mastery),
        },
      })),
    [showMastery],
  );

  const edges = useMemo(() => buildEdges(mockGraph.edges), []);

  // Simplified, non-interactive nodes/edges for the Mini Map preview.
  const overviewNodes = useMemo(
    () =>
      mockGraph.nodes.map((node) => ({
        id: node.id,
        position: node.position,
        data: { label: "" },
        style: {
          width: 10,
          height: 10,
          borderRadius: 9999,
          background: NODE_COLORS[node.type],
          border: "none",
        },
      })),
    [],
  );

  const overviewEdges = useMemo(() => buildOverviewEdges(mockGraph.edges), []);

  const selectedNode = useMemo(
    () => mockGraph.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [selectedNodeId],
  );

  // Learning path steps enriched with each node's type (for pill colors),
  // with the current/root topic prepended as the starting step.
  const learningPath = useMemo(() => {
    const rootNode = mockGraph.nodes.find((n) => n.type === "mainTopic");
    const steps = mockGraph.learningPath.map((step) => {
      const node = mockGraph.nodes.find((n) => n.id === step.id);
      return { ...step, type: node?.type ?? "concept" };
    });
    if (!rootNode) return steps;
    return [
      { id: rootNode.id, label: rootNode.label, type: rootNode.type },
      ...steps,
    ];
  }, []);

  return {
    filterOptions: mockGraph.filterOptions,
    filters,
    updateFilter,
    showMastery,
    setShowMastery,
    nodes,
    edges,
    overviewNodes,
    overviewEdges,
    selectedNode,
    selectedNodeId,
    setSelectedNodeId,
    learningPath,
  };
}
