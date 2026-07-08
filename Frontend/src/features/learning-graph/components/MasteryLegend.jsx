// src/features/learning-graph/components/MasteryLegend.jsx

const MASTERY_DOTS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-yellow-500",
  "bg-teal-500",
  "bg-green-500",
];

export default function MasteryLegend() {
  return (
    <div className="absolute top-3 right-3 flex items-center gap-2 bg-white/90 backdrop-blur-sm border border-slate-100 rounded-full px-3 py-1.5 shadow-sm">
      <span className="text-xs text-slate-500">Low Mastery</span>
      <div className="flex items-center gap-1">
        {MASTERY_DOTS.map((color, i) => (
          <span key={i} className={`w-2 h-2 rounded-full ${color}`} />
        ))}
      </div>
      <span className="text-xs text-slate-500">High Mastery</span>
    </div>
  );
}
