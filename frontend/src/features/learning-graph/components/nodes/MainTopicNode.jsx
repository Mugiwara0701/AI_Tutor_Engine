// src/features/learning-graph/components/nodes/MainTopicNode.jsx

import { Handle, Position } from "reactflow";
import { cn } from "../../../../utils/classNames.js";

export default function MainTopicNode({ data, selected }) {
  return (
    <div
      className={cn(
        "relative px-5 py-3 rounded-xl border-2 border-green-400 bg-green-50 shadow-sm min-w-[150px] text-center cursor-pointer transition-all hover:shadow-md",
        selected && "ring-2 ring-green-300 ring-offset-1",
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
      <p className="text-sm font-semibold text-slate-800">{data.label}</p>
      <Handle
        type="source"
        position={Position.Bottom}
        className="opacity-0 pointer-events-none"
      />
    </div>
  );
}
