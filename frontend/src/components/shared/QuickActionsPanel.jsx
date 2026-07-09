// src/components/shared/QuickActionsPanel.jsx
// Placeholder for QuickActionsPanel — implement component/logic here.

// src/components/shared/QuickActionsPanel.jsx

import { cn } from "../../utils/classNames.js";

/**
 * Generic "Quick Actions" card used on detail pages.
 * actions: [{ label, icon: LucideIcon, onClick }]
 */
export default function QuickActionsPanel({
  title = "Quick Actions",
  actions = [],
  className,
}) {
  return (
    <div
      className={cn(
        "bg-white border border-slate-100 rounded-card p-4",
        className,
      )}
    >
      <h3 className="text-sm font-semibold text-slate-900 mb-3">{title}</h3>
      <div className="flex flex-col gap-1">
        {actions.map((action, i) => (
          <button
            key={i}
            type="button"
            onClick={action.onClick}
            className="flex items-center gap-2.5 px-2.5 py-2 rounded-btn text-sm text-slate-600 hover:bg-slate-50 hover:text-primary transition-colors text-left"
          >
            {action.icon && <action.icon className="w-4 h-4 text-slate-400" />}
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
