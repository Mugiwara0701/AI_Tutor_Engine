// src/components/ui/UserAvatar.jsx
// Placeholder for UserAvatar — implement component/logic here.

import { cn } from "../../utils/classNames.js";

function getInitials(name = "") {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

const SIZE_CLASSES = {
  sm: "w-7 h-7 text-xs",
  md: "w-9 h-9 text-sm",
  lg: "w-11 h-11 text-base",
};

export default function UserAvatar({
  name,
  role,
  avatarUrl,
  size = "md",
  showDetails = false,
  className,
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className={cn(
          "rounded-full bg-indigo-100 text-primary font-semibold flex items-center justify-center overflow-hidden shrink-0",
          SIZE_CLASSES[size],
        )}
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={name}
            className="w-full h-full object-cover"
          />
        ) : (
          <span>{getInitials(name)}</span>
        )}
      </div>
      {showDetails && (
        <div className="min-w-0 text-left">
          <p className="text-sm font-semibold text-slate-800 truncate">
            {name}
          </p>
          {role && <p className="text-xs text-slate-400 truncate">{role}</p>}
        </div>
      )}
    </div>
  );
}
