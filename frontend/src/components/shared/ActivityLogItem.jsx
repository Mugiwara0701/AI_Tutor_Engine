// src/components/shared/ActivityLogItem.jsx
// Placeholder for ActivityLogItem — implement component/logic here.

// src/components/shared/ActivityLogItem.jsx

import UserAvatar from "../ui/UserAvatar.jsx";
import { formatTimeAgo } from "../../utils/formatDate.js";
import { cn } from "../../utils/classNames.js";

const DOT_STYLES = {
  default: "bg-slate-300",
  primary: "bg-primary",
  green: "bg-green-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
  purple: "bg-purple-500",
};

/**
 * Single timestamped entry for activity feeds/logs.
 * Pass `user` to render an avatar, or omit it for a plain colored-dot entry.
 */
export default function ActivityLogItem({
  action,
  description,
  user,
  timestamp,
  color = "default",
  className,
}) {
  return (
    <div className={cn("flex gap-3", className)}>
      {user ? (
        <UserAvatar name={user.name} size="sm" />
      ) : (
        <span className="flex items-center justify-center w-7 h-7 shrink-0">
          <span
            className={cn(
              "w-2 h-2 rounded-full",
              DOT_STYLES[color] ?? DOT_STYLES.default,
            )}
          />
        </span>
      )}
      <div className="min-w-0 flex-1 pb-3 border-b border-slate-50 last:border-b-0 last:pb-0">
        <p className="text-sm text-slate-700">
          {user && (
            <span className="font-medium text-slate-800">{user.name} </span>
          )}
          {action}
        </p>
        {description && (
          <p className="text-xs text-slate-400 mt-0.5">{description}</p>
        )}
        <p className="text-xs text-slate-400 mt-1">
          {formatTimeAgo(timestamp)}
        </p>
      </div>
    </div>
  );
}
