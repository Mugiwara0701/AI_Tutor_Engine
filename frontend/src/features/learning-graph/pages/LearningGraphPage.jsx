// src/features/learning-graph/pages/LearningGraphPage.jsx
// Placeholder for LearningGraphPage — implement component/logic here.

// src/features/learning-graph/pages/LearningGraphPage.jsx

import { ReactFlowProvider } from "reactflow";
import "reactflow/dist/style.css";
import { useGraphData } from "../hooks/useGraphData.js";
import GraphControls from "../components/GraphControls.jsx";
import GraphCanvas from "../components/GraphCanvas.jsx";
import GraphLegend from "../components/GraphLegend.jsx";
import NodeDetailsPanel from "../components/NodeDetailsPanel.jsx";
import LearningPathStrip from "../components/LearningPathStrip.jsx";

export default function LearningGraphPage() {
  const {
    filterOptions,
    filters,
    updateFilter,
    showMastery,
    setShowMastery,
    nodes,
    edges,
    selectedNode,
    setSelectedNodeId,
    learningPath,
  } = useGraphData();

  return (
    <ReactFlowProvider>
      <div className="flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Learning Graph</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Visualize how topics, sub-topics, and concepts connect across the
            curriculum.
          </p>
        </div>

        <GraphControls
          filterOptions={filterOptions}
          filters={filters}
          onFilterChange={updateFilter}
          showMastery={showMastery}
          onToggleMastery={setShowMastery}
        />

        <div className="flex flex-col lg:flex-row gap-5">
          <div className="w-full lg:w-72 shrink-0 flex flex-col gap-5">
            <GraphLegend />
            <NodeDetailsPanel node={selectedNode} />
          </div>

          <GraphCanvas
            nodes={nodes}
            edges={edges}
            onNodeClick={setSelectedNodeId}
            showMastery={showMastery}
          />
        </div>

        <LearningPathStrip path={learningPath} />
      </div>
    </ReactFlowProvider>
  );
}
