// src/layouts/Navbar/Navbar.jsx
// Placeholder for Navbar — implement component/logic here.

import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Bell, HelpCircle } from "lucide-react";
import BreadcrumbNav from "./BreadcrumbNav.jsx";
import UserMenu from "./UserMenu.jsx";
import { useKeyboardShortcut } from "../../hooks/useKeyboardShortcut.js";

export default function Navbar() {
  const searchRef = useRef(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const notificationCount = 6;

  useKeyboardShortcut("k", () => searchRef.current?.focus());

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <header className="sticky top-0 z-10 h-16 bg-white border-b border-slate-100 px-6 flex items-center justify-between gap-6">
      <BreadcrumbNav />

      <div className="flex items-center gap-3 shrink-0">
        <form
          onSubmit={handleSearchSubmit}
          className="relative hidden sm:block"
        >
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            ref={searchRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search (⌘ + K)"
            className="w-64 pl-9 pr-3 py-2 rounded-btn bg-bgLight border border-transparent text-sm placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-slate-200 focus:ring-2 focus:ring-primary/20 transition-colors"
          />
        </form>

        <button
          type="button"
          className="relative p-2 rounded-btn hover:bg-slate-50 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5 text-slate-500" />
          {notificationCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center">
              {notificationCount}
            </span>
          )}
        </button>

        <button
          type="button"
          className="p-2 rounded-btn hover:bg-slate-50 transition-colors"
          aria-label="Help"
        >
          <HelpCircle className="w-5 h-5 text-slate-500" />
        </button>

        <div className="w-px h-6 bg-slate-200" />

        <UserMenu />
      </div>
    </header>
  );
}
