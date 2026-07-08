// src/features/learning-graph/components/nodes/SubTopicNode.jsx

import { Handle, Position } from "reactflow";
import { cn } from "../../../../utils/classNames.js";

export default function SubTopicNode({ data, selected }) {
  return (
    <div
      className={cn(
        "relative px-4 py-3 rounded-xl border border-blue-300 bg-white shadow-sm min-w-[140px] max-w-[180px] text-center cursor-pointer transition-all hover:shadow-md hover:border-blue-400",
        selected && "ring-2 ring-blue-200 ring-offset-1",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="opacity-0 pointer-events-none"
      />
      {data.showMastery && (
        <span
          className={cn(
            "absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full border-2 border-white",
            data.masteryColor,
          )}
        />
      )}
      <p className="text-xs font-semibold text-blue-700 leading-snug">
        {data.label}
      </p>
      <Handle
        type="source"
        position={Position.Bottom}
        className="opacity-0 pointer-events-none"
      />
    </div>
  );
}
