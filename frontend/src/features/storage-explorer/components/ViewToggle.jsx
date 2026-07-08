// src/features/storage-explorer/components/ViewToggle.jsx
// Placeholder for ViewToggle — implement component/logic here.

// src/features/storage-explorer/components/ViewToggle.jsx

import { List, LayoutGrid, Rows3 } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

const VIEWS = [
  { key: "list", icon: List, label: "List view" },
  { key: "grid", icon: LayoutGrid, label: "Grid view" },
  { key: "detail", icon: Rows3, label: "Detail view" },
];

export default function ViewToggle({ value, onChange }) {
  return (
    <div className="flex items-center gap-0.5 p-0.5 bg-slate-100 rounded-btn">
      {VIEWS.map((view) => (
        <button
          key={view.key}
          type="button"
          onClick={() => onChange?.(view.key)}
          aria-label={view.label}
          className={cn(
            "p-1.5 rounded-[6px] transition-colors",
            value === view.key
              ? "bg-white text-primary shadow-sm"
              : "text-slate-400 hover:text-slate-600",
          )}
        >
          <view.icon className="w-4 h-4" />
        </button>
      ))}
    </div>
  );
}
