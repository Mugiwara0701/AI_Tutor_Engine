import { Construction } from "lucide-react";

export default function PlaceholderPage({ title, phase }) {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">{title}</h1>
      <p className="text-slate-500 mb-8">
        This page routes correctly but its UI hasn't been built yet.
      </p>

      <div className="bg-white border border-slate-100 rounded-card p-8 flex flex-col items-center text-center gap-3">
        <div className="w-11 h-11 rounded-full bg-orange-50 flex items-center justify-center">
          <Construction className="w-5 h-5 text-orange-500" />
        </div>
        <p className="text-sm font-medium text-slate-700">Coming in {phase}</p>
        <p className="text-sm text-slate-400 max-w-sm">
          The sidebar and navbar shell (Phase 2) is fully wired up — this page
          will be built out when we get to {phase}.
        </p>
      </div>
    </div>
  );
}
