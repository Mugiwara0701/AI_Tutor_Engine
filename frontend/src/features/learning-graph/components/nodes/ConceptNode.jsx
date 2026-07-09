// src/features/learning-graph/components/nodes/ConceptNode.jsx

import { Handle, Position } from "reactflow";
import { cn } from "../../../../utils/classNames.js";

export default function ConceptNode({ data, selected }) {
  return (
    <div
      className={cn(
        "relative px-3.5 py-2.5 rounded-xl border border-purple-200 bg-purple-50 shadow-sm min-w-[120px] max-w-[160px] text-center cursor-pointer transition-all hover:shadow-md hover:border-purple-300",
        selected && "ring-2 ring-purple-200 ring-offset-1",
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
            "absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full border-2 border-white",
            data.masteryColor,
          )}
        />
      )}
      <p className="text-xs font-medium text-purple-700 leading-snug">
        {data.label}
      </p>
    </div>
  );
}
