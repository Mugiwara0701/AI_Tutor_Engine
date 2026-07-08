// src/components/ui/SparklineChart.jsx

import { cn } from "../../utils/classNames.js";

const STROKE_COLORS = {
  primary: "#2563EB",
  green: "#22c55e",
  orange: "#f97316",
  red: "#ef4444",
  purple: "#a855f7",
  slate: "#94a3b8",
};

/**
 * Minimal inline trend chart. Pass an array of numbers.
 * No dependency on a charting library — a few dozen bytes of SVG.
 */
export default function SparklineChart({
  data = [],
  color = "primary",
  width = 96,
  height = 28,
  className,
}) {
  if (!data.length) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data
    .map((value, i) => {
      const x = (i / (data.length - 1 || 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const stroke = STROKE_COLORS[color] ?? STROKE_COLORS.primary;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("overflow-visible", className)}
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
