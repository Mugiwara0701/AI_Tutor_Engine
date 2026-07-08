// src/features/topics/components/OverviewTab/LearningObjectivesList.jsx
// Placeholder for LearningObjectivesList — implement component/logic here.

// src/features/topics/components/OverviewTab/LearningObjectivesList.jsx

import { CheckCircle2 } from "lucide-react";

export default function LearningObjectivesList({ objectives = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">
        Learning Objectives
      </h3>
      <ul className="flex flex-col gap-2.5">
        {objectives.map((objective, i) => (
          <li
            key={i}
            className="flex items-start gap-2.5 text-sm text-slate-600"
          >
            <CheckCircle2 className="w-4 h-4 text-primary mt-0.5 shrink-0" />
            <span>{objective}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
