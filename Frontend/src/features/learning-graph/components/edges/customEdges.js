// src/features/learning-graph/components/edges/customEdges.js

// Central relation -> visual style map, shared by the canvas and the legend.
export const EDGE_RELATION_STYLES = {
  strong: { stroke: "#475569", dashed: false },
  prerequisite: { stroke: "#94A3B8", dashed: true },
};

/**
 * Builds floating edges for the main interactive canvas — curves attach to
 * whichever side of each node is closest, so they read naturally in a radial layout.
 */
export function buildEdges(rawEdges = []) {
  return rawEdges.map((edge) => {
    const style =
      EDGE_RELATION_STYLES[edge.relation] ?? EDGE_RELATION_STYLES.prerequisite;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "floating",
      style: {
        stroke: style.stroke,
        strokeWidth: 1.5,
        strokeDasharray: style.dashed ? "5 4" : undefined,
      },
      markerEnd: {
        type: "arrowclosed",
        color: style.stroke,
        width: 14,
        height: 14,
      },
    };
  });
}

/**
 * Builds simplified, non-interactive edges for the Mini Map preview.
 */
export function buildOverviewEdges(rawEdges = []) {
  return rawEdges.map((edge) => ({
    id: `overview-${edge.id}`,
    source: edge.source,
    target: edge.target,
    type: "straight",
    style: { stroke: "#E2E8F0", strokeWidth: 1 },
  }));
}
