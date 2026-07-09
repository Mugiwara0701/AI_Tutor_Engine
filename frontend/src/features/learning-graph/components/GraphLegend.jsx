// src/features/learning-graph/components/GraphLegend.jsx

const NODE_TYPES = [
  { label: "Main Topic", color: "bg-green-500" },
  { label: "Sub Topic", color: "bg-blue-600" },
  { label: "Concept", color: "bg-purple-500" },
];

const EDGE_TYPES = [
  { label: "Prerequisite", style: "solid" },
  { label: "Strong Connection", style: "solid" },
  { label: "Related", style: "dashed" },
];

function EdgeSwatch({ style }) {
  return (
    <svg width="20" height="10" viewBox="0 0 20 10" className="shrink-0">
      <line
        x1="1"
        y1="5"
        x2="15"
        y2="5"
        stroke="#94A3B8"
        strokeWidth="1.5"
        strokeDasharray={style === "dashed" ? "3 2" : "0"}
      />
      <polygon points="15,2 19,5 15,8" fill="#94A3B8" />
    </svg>
  );
}

export default function GraphLegend() {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-900">Legend</h3>

      <div className="flex flex-col gap-2">
        {NODE_TYPES.map(({ label, color }) => (
          <div
            key={label}
            className="flex items-center gap-2 text-sm text-slate-600"
          >
            <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${color}`} />
            {label}
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
        {EDGE_TYPES.map(({ label, style }) => (
          <div
            key={label}
            className="flex items-center gap-2 text-sm text-slate-600"
          >
            <EdgeSwatch style={style} />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
