// src/components/ui/Checkbox.jsx
// Placeholder for Checkbox — implement component/logic here.

// src/components/ui/Checkbox.jsx

import { Check } from "lucide-react";
import { cn } from "../../utils/classNames.js";

export default function Checkbox({ checked, onChange, label, className }) {
  return (
    <label
      className={cn(
        "inline-flex items-center gap-2 cursor-pointer select-none",
        className,
      )}
    >
      <span
        role="checkbox"
        aria-checked={checked}
        tabIndex={0}
        onClick={() => onChange?.(!checked)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onChange?.(!checked);
          }
        }}
        className={cn(
          "w-4 h-4 rounded flex items-center justify-center border transition-colors shrink-0",
          checked ? "bg-primary border-primary" : "bg-white border-slate-300",
        )}
      >
        {checked && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
      </span>
      {label && <span className="text-sm text-slate-600">{label}</span>}
    </label>
  );
}
