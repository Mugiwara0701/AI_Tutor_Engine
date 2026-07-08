// src/components/ui/DataTable/TableHeader.jsx
// Placeholder for TableHeader — implement component/logic here.

// src/components/ui/DataTable/TableHeader.jsx

import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

export default function TableHeader({
  columns,
  sort,
  onSort,
  selectable,
  allSelected,
  onToggleAll,
}) {
  return (
    <thead>
      <tr className="border-b border-slate-100">
        {selectable && (
          <th className="w-10 px-4 py-3">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={(e) => onToggleAll?.(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary/30"
            />
          </th>
        )}
        {columns.map((col) => (
          <th
            key={col.key}
            className={cn(
              "px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap",
              col.align === "right" && "text-right",
            )}
            style={col.width ? { width: col.width } : undefined}
          >
            {col.sortable ? (
              <button
                type="button"
                onClick={() => onSort?.(col.key)}
                className="inline-flex items-center gap-1 hover:text-slate-700 transition-colors"
              >
                {col.label}
                {sort?.key === col.key ? (
                  sort.direction === "asc" ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )
                ) : (
                  <ChevronsUpDown className="w-3.5 h-3.5 text-slate-300" />
                )}
              </button>
            ) : (
              col.label
            )}
          </th>
        ))}
      </tr>
    </thead>
  );
}
