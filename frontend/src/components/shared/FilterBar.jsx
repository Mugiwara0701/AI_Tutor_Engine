// src/components/shared/FilterBar.jsx
// Placeholder for FilterBar — implement component/logic here.

// src/components/shared/FilterBar.jsx

import { X } from "lucide-react";
import Dropdown from "../ui/Dropdown.jsx";
import { cn } from "../../utils/classNames.js";

/**
 * Row of filter dropdowns, generated from config.
 * filters: [{ key, label, options: string[] }]
 * values: { [key]: string }
 * onChange: (key, value) => void
 */
export default function FilterBar({
  filters = [],
  values = {},
  onChange,
  onClear,
  className,
}) {
  const hasActiveFilters = Object.values(values).some((v) => v);

  return (
    <div className={cn("flex flex-wrap items-center gap-2.5", className)}>
      {filters.map((filter) => (
        <Dropdown
          key={filter.key}
          label={filter.label}
          value={values[filter.key]}
          onChange={(value) => onChange?.(filter.key, value)}
          options={filter.options}
          className="min-w-[140px]"
        />
      ))}

      {hasActiveFilters && onClear && (
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          Clear filters
        </button>
      )}
    </div>
  );
}
