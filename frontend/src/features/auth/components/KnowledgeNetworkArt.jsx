// src/features/auth/components/KnowledgeNetworkArt.jsx
//
// Purely decorative. An abstract constellation of connected nodes standing
// in for "knowledge graph" without mimicking any real app screen — replaces
// the previous mock-dashboard-style preview per the design brief
// (no large dashboards / random graphs on the auth brand panel).

const NODES = [
  { x: 60, y: 48, r: 4, emphasis: false },
  { x: 150, y: 24, r: 5, emphasis: false },
  { x: 246, y: 46, r: 4, emphasis: false },
  { x: 40, y: 140, r: 4.5, emphasis: false },
  { x: 152, y: 118, r: 9, emphasis: true },
  { x: 268, y: 132, r: 5, emphasis: false },
  { x: 96, y: 208, r: 4, emphasis: false },
  { x: 200, y: 214, r: 4.5, emphasis: false },
  { x: 292, y: 196, r: 4, emphasis: false },
];

const EDGES = [
  [0, 1],
  [1, 2],
  [0, 3],
  [1, 4],
  [2, 5],
  [3, 4],
  [4, 5],
  [3, 6],
  [4, 7],
  [5, 8],
  [6, 7],
  [7, 8],
];

export default function KnowledgeNetworkArt({ className }) {
  return (
    <svg
      viewBox="0 0 320 260"
      className={className}
      role="img"
      aria-label="Abstract illustration of connected knowledge nodes"
    >
      {EDGES.map(([a, b], i) => (
        <line
          key={i}
          x1={NODES[a].x}
          y1={NODES[a].y}
          x2={NODES[b].x}
          y2={NODES[b].y}
          stroke="rgba(148,163,184,0.35)"
          strokeWidth="1"
        />
      ))}

      {NODES.map((node, i) => (
        <circle
          key={i}
          cx={node.x}
          cy={node.y}
          r={node.r}
          fill={node.emphasis ? "#60A5FA" : "rgba(226,232,240,0.85)"}
          stroke={node.emphasis ? "rgba(96,165,250,0.35)" : "none"}
          strokeWidth={node.emphasis ? 8 : 0}
        />
      ))}
    </svg>
  );
}
