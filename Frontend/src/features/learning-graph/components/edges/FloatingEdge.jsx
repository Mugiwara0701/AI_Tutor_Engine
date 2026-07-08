// src/features/learning-graph/components/edges/FloatingEdge.jsx

import { useStore, getBezierPath } from "reactflow";
import { getFloatingEdgeParams } from "./floatingEdgeUtils.js";

export default function FloatingEdge({ id, source, target, markerEnd, style }) {
  const sourceNode = useStore((s) => s.nodeInternals.get(source));
  const targetNode = useStore((s) => s.nodeInternals.get(target));

  if (!sourceNode?.width || !targetNode?.width) return null;

  const { sx, sy, tx, ty, sourcePosition, targetPosition } =
    getFloatingEdgeParams(sourceNode, targetNode);

  const [edgePath] = getBezierPath({
    sourceX: sx,
    sourceY: sy,
    sourcePosition,
    targetX: tx,
    targetY: ty,
    targetPosition,
  });

  return (
    <path
      id={id}
      className="react-flow__edge-path"
      d={edgePath}
      markerEnd={markerEnd}
      style={style}
    />
  );
}
