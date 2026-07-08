// src/features/learning-graph/components/MiniMapPanel.jsx
// Placeholder for MiniMapPanel — implement component/logic here.

// src/features/learning-graph/components/MiniMapPanel.jsx

import ReactFlow, { Background, ReactFlowProvider } from "reactflow";

/**
 * Renders a small, read-only preview of the graph. Uses its own isolated
 * ReactFlowProvider so it doesn't share zoom/viewport state with the main canvas.
 */
export default function MiniMapPanel({ nodes = [], edges = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-3">
      <h3 className="text-sm font-semibold text-slate-900 mb-2">Mini Map</h3>
      <div className="h-32 rounded-btn overflow-hidden border border-slate-100 bg-slate-50">
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={12} size={1} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </div>
  );
}
