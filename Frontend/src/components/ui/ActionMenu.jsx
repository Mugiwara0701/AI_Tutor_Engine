// src/components/ui/ActionMenu.jsx
// Placeholder for ActionMenu — implement component/logic here.

// src/components/ui/ActionMenu.jsx

import { useEffect, useRef, useState } from "react";
import { MoreVertical } from "lucide-react";
import { cn } from "../../utils/classNames.js";

/**
 * Three-dot dropdown menu.
 * items: [{ label, icon: LucideIcon, onClick, danger?: boolean }]
 */
export default function ActionMenu({ items = [], align = "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="p-1.5 rounded-btn hover:bg-slate-100 transition-colors"
        aria-label="More actions"
      >
        <MoreVertical className="w-4 h-4 text-slate-400" />
      </button>

      {open && (
        <div
          className={cn(
            "absolute top-full mt-1 w-48 bg-white border border-slate-100 rounded-card shadow-lg py-1 z-20",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {items.map((item, i) => (
            <button
              key={i}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                item.onClick?.();
                setOpen(false);
              }}
              className={cn(
                "w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left transition-colors",
                item.danger
                  ? "text-red-600 hover:bg-red-50"
                  : "text-slate-600 hover:bg-slate-50",
              )}
            >
              {item.icon && <item.icon className="w-4 h-4" />}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
