// src/components/ui/EmptyState.jsx
// Placeholder for EmptyState — implement component/logic here.

// src/components/ui/EmptyState.jsx

import { Inbox } from "lucide-react";
import { cn } from "../../utils/classNames.js";

export default function EmptyState({
  icon: Icon = Inbox,
  title = "Nothing here yet",
  description,
  action,
  className,
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center text-center gap-3 py-12 px-6",
        className,
      )}
    >
      <div className="w-11 h-11 rounded-full bg-slate-50 flex items-center justify-center">
        <Icon className="w-5 h-5 text-slate-400" />
      </div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {description && (
        <p className="text-sm text-slate-400 max-w-sm">{description}</p>
      )}
      {action}
    </div>
  );
}
