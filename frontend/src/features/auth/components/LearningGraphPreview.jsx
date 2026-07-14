import { GraduationCap, BarChart3 } from "lucide-react";

const NODES = [
  { label: "Lesson Plan", sub: "AI Generated", top: "8%", left: "58%" },
  { label: "Assessment", sub: "Auto-Generated", top: "30%", left: "84%" },
  { label: "Learning Objectives", sub: "", top: "30%", left: "12%" },
  { label: "Study Materials", sub: "Curated", top: "68%", left: "8%" },
  { label: "Student Progress", sub: "Tracked", top: "68%", left: "82%" },
  { label: "Content Outline", sub: "", top: "88%", left: "45%" },
];

export default function LearningGraphPreview() {
  return (
    <div className="relative w-full max-w-lg bg-white rounded-2xl border border-slate-100 shadow-sm p-4 overflow-visible">
      <div className="flex gap-3">
        {/* Left mini sidebar strip (mimics the app's own sidebar) */}
        <div className="flex flex-col items-center gap-2.5 pt-0.5">
          <div className="w-6 h-6 rounded-md bg-primary flex items-center justify-center text-[10px] text-white font-bold">
            M
          </div>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="w-4 h-4 rounded bg-slate-100" />
          ))}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-500 mb-3">
            Learning Graph
          </p>

          <div className="relative h-44">
            {NODES.map((node) => (
              <div
                key={node.label}
                className="absolute -translate-x-1/2 -translate-y-1/2 bg-emerald-50 border border-emerald-100 rounded-lg px-2.5 py-1.5 text-center shadow-sm z-10"
                style={{ top: node.top, left: node.left }}
              >
                <p className="text-[10px] font-semibold text-slate-700 whitespace-nowrap leading-tight">
                  {node.label}
                </p>
                {node.sub && (
                  <p className="text-[9px] text-slate-400 whitespace-nowrap leading-tight">
                    {node.sub}
                  </p>
                )}
              </div>
            ))}

            {/* Center node */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-primary rounded-lg px-3.5 py-2 shadow-md z-20">
              <p className="text-[11px] font-semibold text-white whitespace-nowrap">
                Course Overview
              </p>
            </div>

            <svg className="absolute inset-0 w-full h-full" aria-hidden="true">
              {NODES.map((node, i) => (
                <line
                  key={i}
                  x1="50%"
                  y1="50%"
                  x2={node.left}
                  y2={node.top}
                  stroke="#CBD5E1"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
              ))}
            </svg>
          </div>
        </div>
      </div>

      {/* Floating graduation cap badge */}
      <div className="absolute -right-4 -top-4 w-12 h-12 rounded-2xl bg-indigo-500 shadow-lg flex items-center justify-center">
        <GraduationCap className="w-5 h-5 text-white" />
      </div>

      {/* Floating bar chart badge */}
      <div className="absolute -left-4 bottom-8 w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center shadow-sm">
        <BarChart3 className="w-4.5 h-4.5 text-indigo-500" />
      </div>
    </div>
  );
}
