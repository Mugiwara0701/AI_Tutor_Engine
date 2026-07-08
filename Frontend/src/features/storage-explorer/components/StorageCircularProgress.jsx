// src/features/storage-explorer/components/StorageCircularProgress.jsx
// Placeholder for StorageCircularProgress — implement component/logic here.

// src/features/storage-explorer/components/StorageCircularProgress.jsx

import { formatGB } from "../../../utils/formatBytes.js";

export default function StorageCircularProgress({ usedGB, totalGB }) {
  const percentage = totalGB > 0 ? Math.round((usedGB / totalGB) * 100) : 0;
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;
  const color =
    percentage > 90 ? "#ef4444" : percentage > 70 ? "#f97316" : "#2563EB";

  return (
    <div className="flex flex-col items-center gap-2 p-3">
      <div className="relative w-28 h-28">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="#f1f5f9"
            strokeWidth="9"
          />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.4s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-slate-900">
            {percentage}%
          </span>
          <span className="text-[11px] text-slate-400">used</span>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        {formatGB(usedGB)} / {formatGB(totalGB)}
      </p>

      <a href="#" className="text-xs font-medium text-primary hover:underline">
        View Details
      </a>
    </div>
  );
}
