// src/layouts/Sidebar/Sidebar.jsx

import { useEffect } from "react";
import { Sparkles, X } from "lucide-react";
import { SIDEBAR_NAV } from "./sidebarConfig.js";
import SidebarNavItem from "./SidebarNavItem.jsx";
import { useAuth } from "../../features/auth/hooks/useAuth.js";
import { useLocation } from "react-router-dom";
import { useSidebar } from "../../hooks/useSidebar.js";
import { cn } from "../../utils/classNames.js";

export default function Sidebar() {
  const { user } = useAuth();
  const location = useLocation();
  const { isMobileOpen, closeMobileSidebar } = useSidebar();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    closeMobileSidebar();
  }, [location.pathname, closeMobileSidebar]);

  // Hide nav items restricted to specific roles (e.g. Settings is
  // admin/manager only) — items with no `roles` list are visible to
  // everyone.
  const visibleNav = SIDEBAR_NAV.filter(
    (item) => !item.roles || item.roles.includes(user?.role),
  );

  return (
    <>
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 md:hidden"
          onClick={closeMobileSidebar}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col w-[220px] h-screen bg-white border-r border-slate-100 transition-transform duration-200 ease-out",
          "md:sticky md:top-0 md:z-0 md:translate-x-0 md:shrink-0",
          isMobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-2 px-4 h-16 border-b border-slate-100">
          <div className="relative w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <span className="text-white font-bold text-sm">M</span>
            <Sparkles className="w-3 h-3 text-yellow-300 absolute -top-1 -right-1" />
          </div>
          <span className="text-base font-semibold text-slate-900 flex-1">
            AI Tutor
          </span>
          <button
            type="button"
            onClick={closeMobileSidebar}
            className="md:hidden p-1.5 rounded-btn hover:bg-slate-50 transition-colors"
            aria-label="Close menu"
          >
            <X className="w-4.5 h-4.5 text-slate-500" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto no-scrollbar px-3 py-4 space-y-1">
          {visibleNav.map((item) => (
            <SidebarNavItem key={item.key} item={item} />
          ))}
        </nav>
      </aside>
    </>
  );
}
