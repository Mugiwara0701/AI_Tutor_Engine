// src/components/ui/Dropdown.jsx

import { ChevronDown } from "lucide-react";
import { cn } from "../../utils/classNames.js";

/**
 * Simple native-select-based dropdown styled to match the design system.
 * Usage: <Dropdown label="Class" value={value} onChange={setValue} options={["Class 12", "Class 11"]} />
 * `options` can be an array of strings, or an array of { label, value } objects.
 */
export default function Dropdown({
  label,
  value,
  onChange,
  options = [],
  placeholder = "All",
  disabled = false,
  className,
}) {
  const normalized = options.map((opt) =>
    typeof opt === "string" ? { label: opt, value: opt } : opt,
  );

  return (
    <div className={cn("relative", className)}>
      <select
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
        className={cn(
          "appearance-none w-full pl-3 pr-8 py-2 rounded-btn border border-slate-200 bg-white text-sm text-slate-700",
          "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors",
          disabled
            ? "bg-slate-50 text-slate-400 cursor-not-allowed"
            : "hover:border-slate-300 cursor-pointer",
        )}
        aria-label={label}
      >
        <option value="">
          {label ? `${label}: ${placeholder}` : placeholder}
        </option>
        {normalized.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
    </div>
  );
}
