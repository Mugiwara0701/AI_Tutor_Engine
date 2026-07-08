// src/features/learning-graph/components/GraphCanvas.jsx

import ReactFlow from "reactflow";
import MainTopicNode from "./nodes/MainTopicNode.jsx";
import SubTopicNode from "./nodes/SubTopicNode.jsx";
import ConceptNode from "./nodes/ConceptNode.jsx";
import FloatingEdge from "./edges/FloatingEdge.jsx";
import MasteryLegend from "./MasteryLegend.jsx";

const nodeTypes = {
  mainTopic: MainTopicNode,
  subTopic: SubTopicNode,
  concept: ConceptNode,
};

const edgeTypes = {
  floating: FloatingEdge,
};

export default function GraphCanvas({
  nodes,
  edges,
  onNodeClick,
  showMastery,
}) {
  return (
    <div className="relative flex-1 h-[560px] bg-white border border-slate-100 rounded-card overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        nodesConnectable={false}
        edgesUpdatable={false}
        fitView
        proOptions={{ hideAttribution: true }}
      />
      {showMastery && <MasteryLegend />}
    </div>
  );
}
