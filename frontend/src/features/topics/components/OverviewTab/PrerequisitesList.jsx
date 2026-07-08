// src/features/topics/components/OverviewTab/PrerequisitesList.jsx
// Placeholder for PrerequisitesList — implement component/logic here.

// src/features/topics/components/OverviewTab/PrerequisitesList.jsx

import { ChevronRight } from "lucide-react";

export default function PrerequisitesList({ prerequisites = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">
        Prerequisites
      </h3>
      <ol className="flex flex-col">
        {prerequisites.map((item, i) => (
          <li key={item.id}>
            <button
              type="button"
              className="w-full flex items-center justify-between gap-2 py-2 text-sm text-slate-600 hover:text-primary transition-colors group"
            >
              <span className="flex items-center gap-2.5">
                <span className="w-5 h-5 rounded-full bg-slate-100 text-xs font-medium text-slate-500 flex items-center justify-center shrink-0">
                  {i + 1}
                </span>
                {item.name}
              </span>
              <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-primary shrink-0" />
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
