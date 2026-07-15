// src/layouts/Sidebar/Sidebar.jsx

import { useState, useRef, useEffect } from "react";
import { Sparkles, ChevronDown, LogOut, UserCircle, X } from "lucide-react";
import { SIDEBAR_NAV } from "./sidebarConfig.js";
import SidebarNavItem from "./SidebarNavItem.jsx";
import UserAvatar from "../../components/ui/UserAvatar.jsx";
import { useAuth } from "../../features/auth/hooks/useAuth.js";
import { useNavigate, useLocation } from "react-router-dom";
import { useSidebar } from "../../hooks/useSidebar.js";
import { cn } from "../../utils/classNames.js";

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const { isMobileOpen, closeMobileSidebar } = useSidebar();

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    closeMobileSidebar();
  }, [location.pathname, closeMobileSidebar]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

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
          {SIDEBAR_NAV.filter(
            (item) =>
              !item.roles ||
              item.roles.includes((user?.role || "").trim().toLowerCase()),
          ).map((item) => (
            <SidebarNavItem key={item.key} item={item} />
          ))}
        </nav>

        <div className="relative border-t border-slate-100 p-3" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="w-full flex items-center justify-between gap-2 px-2 py-2 rounded-btn hover:bg-slate-50 transition-colors"
          >
            <UserAvatar
              name={user?.name ?? "Guest User"}
              role={user?.role ?? "Signed out"}
              avatarUrl={user?.avatarUrl}
              showDetails
            />
            <ChevronDown
              className={`w-4 h-4 text-slate-400 shrink-0 transition-transform ${
                menuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {menuOpen && (
            <div className="absolute bottom-full left-3 right-3 mb-2 bg-white border border-slate-100 rounded-card shadow-lg overflow-hidden">
              <button
                type="button"
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                <UserCircle className="w-4 h-4 text-slate-400" />
                View profile
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-red-600 hover:bg-red-50 border-t border-slate-100"
              >
                <LogOut className="w-4 h-4" />
                Log out
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
