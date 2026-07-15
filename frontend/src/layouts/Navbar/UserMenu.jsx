// src/layouts/Navbar/UserMenu.jsx
// Placeholder for UserMenu — implement component/logic here.

import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, UserCircle, Settings, LogOut, KeyRound } from "lucide-react";
import UserAvatar from "../../components/ui/UserAvatar.jsx";
import { useAuth } from "../../features/auth/hooks/useAuth.js";
import ResetPasswordModal from "./ResetPasswordModal.jsx";

export default function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [resetPasswordOpen, setResetPasswordOpen] = useState(false);
  const ref = useRef(null);
  // Settings (Employee/User Management) is admin/manager only - see
  // RequireRole on the /settings route. Hide the links here too so a
  // "user" doesn't click through to a page that just bounces them back.
  const canAccessSettings = ["admin", "manager"].includes(
    (user?.role || "").trim().toLowerCase(),
  );

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 pl-1 pr-2 py-1 rounded-btn hover:bg-slate-50 transition-colors"
      >
        <UserAvatar
          name={user?.name ?? "Guest"}
          avatarUrl={user?.avatarUrl}
          size="sm"
        />
        <ChevronDown
          className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-52 bg-white border border-slate-100 rounded-card shadow-lg overflow-hidden z-20">
          <div className="px-3.5 py-3 border-b border-slate-100">
            <p className="text-sm font-semibold text-slate-800 truncate">
              {user?.name ?? "Guest User"}
            </p>
            <p className="text-xs text-slate-400 truncate">
              {user?.email ?? "Not signed in"}
            </p>
          </div>
          {canAccessSettings && (
            <button
              onClick={() => {
                setOpen(false);
                navigate("/settings");
              }}
              className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <UserCircle className="w-4 h-4 text-slate-400" />
              View profile
            </button>
          )}
          {canAccessSettings && (
            <button
              onClick={() => {
                setOpen(false);
                navigate("/settings");
              }}
              className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              <Settings className="w-4 h-4 text-slate-400" />
              Settings
            </button>
          )}
          <button
            onClick={() => {
              setOpen(false);
              setResetPasswordOpen(true);
            }}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            <KeyRound className="w-4 h-4 text-slate-400" />
            Reset Password
          </button>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-red-600 hover:bg-red-50 border-t border-slate-100"
          >
            <LogOut className="w-4 h-4" />
            Log out
          </button>
        </div>
      )}

      <ResetPasswordModal
        open={resetPasswordOpen}
        onClose={() => setResetPasswordOpen(false)}
      />
    </div>
  );
}
