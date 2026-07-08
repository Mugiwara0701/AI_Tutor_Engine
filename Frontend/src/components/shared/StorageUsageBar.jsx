// src/components/shared/StorageUsageBar.jsx
// Placeholder for StorageUsageBar — implement component/logic here.

// src/components/shared/StorageUsageBar.jsx

import { HardDrive } from "lucide-react";
import ProgressBar from "../ui/ProgressBar.jsx";
import { formatGB } from "../../utils/formatBytes.js";
import { cn } from "../../utils/classNames.js";

export default function StorageUsageBar({ usedGB, totalGB, className }) {
  const percentage = totalGB > 0 ? (usedGB / totalGB) * 100 : 0;
  const color =
    percentage > 90 ? "red" : percentage > 70 ? "orange" : "primary";

  return (
    <div className={cn("p-3 rounded-card bg-bgLight", className)}>
      <div className="flex items-center gap-2 mb-2 text-xs text-slate-500">
        <HardDrive className="w-3.5 h-3.5" />
        <span>Storage used</span>
      </div>
      <ProgressBar
        value={percentage}
        showPercentage={false}
        color={color}
        size="sm"
      />
      <div className="flex items-center justify-between mt-1.5 text-xs">
        <span className="text-slate-600 font-medium">
          {formatGB(usedGB)} / {formatGB(totalGB)}
        </span>
        <span className="text-slate-400">{Math.round(percentage)}%</span>
      </div>
    </div>
  );
}
