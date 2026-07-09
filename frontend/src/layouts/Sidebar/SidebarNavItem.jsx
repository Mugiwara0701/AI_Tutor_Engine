// src/layouts/Sidebar/SidebarNavItem.jsx
// Placeholder for SidebarNavItem — implement component/logic here.

import { NavLink, useLocation } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "../../utils/classNames.js";
import { useSidebar } from "../../hooks/useSidebar.js";

export default function SidebarNavItem({ item }) {
  const { icon: Icon, label, path, children, key } = item;
  const location = useLocation();
  const { expandedGroups, toggleGroup } = useSidebar();
  const hasChildren = Boolean(children?.length);
  const isExpanded = expandedGroups[key];

  const isParentActive =
    location.pathname === path || location.pathname.startsWith(`${path}/`);

  return (
    <div>
      <NavLink
        to={path}
        onClick={() => {
          if (hasChildren && !isExpanded) toggleGroup(key);
        }}
        className={({ isActive }) =>
          cn(
            "group flex items-center justify-between gap-2 px-3 py-2 rounded-btn text-sm font-medium transition-colors",
            isActive || isParentActive
              ? "bg-blue-50 text-primary"
              : "text-slate-600 hover:bg-slate-50",
          )
        }
      >
        <span className="flex items-center gap-2.5">
          <Icon
            className={cn(
              "w-4.5 h-4.5",
              isParentActive ? "text-primary" : "text-slate-400",
            )}
            size={18}
          />
          {label}
        </span>

        {hasChildren && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              toggleGroup(key);
            }}
            className="p-0.5 rounded hover:bg-slate-200/60"
            aria-label={isExpanded ? "Collapse" : "Expand"}
          >
            <ChevronDown
              className={cn(
                "w-3.5 h-3.5 text-slate-400 transition-transform",
                isExpanded && "rotate-180",
              )}
            />
          </button>
        )}
      </NavLink>

      {hasChildren && isExpanded && (
        <div className="mt-1 ml-6 pl-3 border-l border-slate-100 space-y-0.5">
          {children.map((child) => (
            <NavLink
              key={child.key}
              to={child.path}
              end
              className={({ isActive }) =>
                cn(
                  "block px-2.5 py-1.5 rounded-btn text-sm transition-colors",
                  isActive
                    ? "text-primary font-medium bg-blue-50"
                    : "text-slate-500 hover:bg-slate-50",
                )
              }
            >
              {child.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}
