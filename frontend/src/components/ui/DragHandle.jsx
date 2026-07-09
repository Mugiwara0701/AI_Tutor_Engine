// src/components/ui/DragHandle.jsx

import { GripVertical } from "lucide-react";
import { cn } from "../../utils/classNames.js";

/**
 * Six-dot drag handle for reorderable list/table rows.
 * Spread dnd-kit's `attributes` and `listeners` onto this component.
 */
export default function DragHandle({ className, ...dragProps }) {
  return (
    <button
      type="button"
      className={cn(
        "flex items-center justify-center w-6 h-6 rounded text-slate-300 hover:text-slate-500 hover:bg-slate-100 cursor-grab active:cursor-grabbing transition-colors touch-none",
        className,
      )}
      aria-label="Drag to reorder"
      {...dragProps}
    >
      <GripVertical className="w-4 h-4" />
    </button>
  );
}
