// src/features/learning-graph/components/edges/floatingEdgeUtils.js

import { Position } from "reactflow";

const EDGE_GAP = 6; // px gap kept between the node border and the edge/arrowhead

// Finds where the line from `from`'s center to `to`'s center crosses `from`'s rectangle.
function getBorderPoint(from, to) {
  const w = from.width / 2;
  const h = from.height / 2;
  const cx = from.positionAbsolute.x + w;
  const cy = from.positionAbsolute.y + h;
  const tx = to.positionAbsolute.x + to.width / 2;
  const ty = to.positionAbsolute.y + to.height / 2;

  const dx = (tx - cx) / (2 * w) - (ty - cy) / (2 * h);
  const dy = (tx - cx) / (2 * w) + (ty - cy) / (2 * h);
  const scale = 1 / (Math.abs(dx) + Math.abs(dy) || 1);

  return {
    x: w * (scale * dx + scale * dy) + cx,
    y: h * (-scale * dx + scale * dy) + cy,
  };
}

// Pulls a border point back toward its node's center by a fixed gap, so the
// edge/arrowhead doesn't visually touch the node border.
function applyGap(point, node) {
  const cx = node.positionAbsolute.x + node.width / 2;
  const cy = node.positionAbsolute.y + node.height / 2;
  const vx = point.x - cx;
  const vy = point.y - cy;
  const len = Math.hypot(vx, vy) || 1;

  return {
    x: point.x - (vx / len) * EDGE_GAP,
    y: point.y - (vy / len) * EDGE_GAP,
  };
}

function getSide(node, point) {
  const x = Math.round(point.x);
  const y = Math.round(point.y);
  const nx = Math.round(node.positionAbsolute.x);
  const ny = Math.round(node.positionAbsolute.y);

  if (x <= nx + 1) return Position.Left;
  if (x >= nx + node.width - 1) return Position.Right;
  if (y <= ny + 1) return Position.Top;
  if (y >= ny + node.height - 1) return Position.Bottom;
  return Position.Top;
}

/**
 * Given two React Flow internal node objects (with width/height/positionAbsolute
 * already measured by React Flow), returns the exact points and sides where a
 * connector should attach — regardless of which direction the nodes sit from each other.
 */
export function getFloatingEdgeParams(sourceNode, targetNode) {
  const sourceBorderPoint = getBorderPoint(sourceNode, targetNode);
  const targetBorderPoint = getBorderPoint(targetNode, sourceNode);

  const sourcePoint = applyGap(sourceBorderPoint, sourceNode);
  const targetPoint = applyGap(targetBorderPoint, targetNode);

  return {
    sx: sourcePoint.x,
    sy: sourcePoint.y,
    tx: targetPoint.x,
    ty: targetPoint.y,
    sourcePosition: getSide(sourceNode, sourceBorderPoint),
    targetPosition: getSide(targetNode, targetBorderPoint),
  };
}
