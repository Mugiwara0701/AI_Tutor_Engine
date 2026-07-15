// src/layouts/Navbar/Navbar.jsx

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Bell,
  HelpCircle,
  Menu,
  UploadCloud,
  AlertTriangle,
  HardDrive,
  UserPlus,
  CheckCheck,
} from "lucide-react";
import BreadcrumbNav from "./BreadcrumbNav.jsx";
import UserMenu from "./UserMenu.jsx";
import EmptyState from "../../components/ui/EmptyState.jsx";
import { useKeyboardShortcut } from "../../hooks/useKeyboardShortcut.js";
import { useSidebar } from "../../hooks/useSidebar.js";
import { formatTimeAgo } from "../../utils/formatDate.js";
import { cn } from "../../utils/classNames.js";

// Mock notification feed — in a real app this would come from a
// notifications API/websocket. Kept inline here since no notifications
// feature/data source exists elsewhere in the app yet.
const INITIAL_NOTIFICATIONS = [
  {
    id: "n1",
    type: "ingestion",
    title: "Ingestion complete",
    message: '"Physics Class 10 - Chapter 4" finished processing.',
    timestamp: "2026-07-15T09:40:00Z",
    read: false,
  },
  {
    id: "n2",
    type: "pipeline",
    title: "Pipeline failed",
    message: 'Concept extraction failed for "Chemistry Class 9 - Chapter 2".',
    timestamp: "2026-07-15T07:15:00Z",
    read: false,
  },
  {
    id: "n3",
    type: "storage",
    title: "Storage usage high",
    message: "Storage is at 92% capacity. Consider archiving old zips.",
    timestamp: "2026-07-14T18:05:00Z",
    read: false,
  },
  {
    id: "n4",
    type: "member",
    title: "New team member",
    message: "Aisha Khan was added as an Editor.",
    timestamp: "2026-07-14T11:30:00Z",
    read: true,
  },
  {
    id: "n5",
    type: "ingestion",
    title: "Ingestion complete",
    message: '"Biology Class 11 - Chapter 1" finished processing.',
    timestamp: "2026-07-13T14:00:00Z",
    read: true,
  },
];

const NOTIFICATION_ICONS = {
  ingestion: { icon: UploadCloud, className: "bg-blue-50 text-primary" },
  pipeline: { icon: AlertTriangle, className: "bg-red-50 text-red-600" },
  storage: { icon: HardDrive, className: "bg-orange-50 text-orange-600" },
  member: { icon: UserPlus, className: "bg-green-50 text-green-600" },
};

export default function Navbar() {
  const searchRef = useRef(null);
  const notificationsRef = useRef(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [notifications, setNotifications] = useState(INITIAL_NOTIFICATIONS);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationCount = notifications.filter((n) => !n.read).length;
  const { openMobileSidebar } = useSidebar();

  useKeyboardShortcut("k", () => searchRef.current?.focus());

  useEffect(() => {
    function handleClickOutside(e) {
      if (
        notificationsRef.current &&
        !notificationsRef.current.contains(e.target)
      ) {
        setNotificationsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const markAllAsRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const markAsRead = (id) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <header className="sticky top-0 z-10 h-16 bg-white border-b border-slate-100 px-4 sm:px-6 flex items-center justify-between gap-6">
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={openMobileSidebar}
          className="md:hidden shrink-0 p-2 -ml-2 rounded-btn hover:bg-slate-50 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5 text-slate-600" />
        </button>
        <BreadcrumbNav />
      </div>

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

        <div className="relative" ref={notificationsRef}>
          <button
            type="button"
            onClick={() => setNotificationsOpen((v) => !v)}
            className="relative p-2 rounded-btn hover:bg-slate-50 transition-colors"
            aria-label="Notifications"
            aria-expanded={notificationsOpen}
          >
            <Bell className="w-5 h-5 text-slate-500" />
            {notificationCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center">
                {notificationCount > 9 ? "9+" : notificationCount}
              </span>
            )}
          </button>

          {notificationsOpen && (
            <div className="absolute right-0 top-full mt-2 w-80 bg-white border border-slate-200 rounded-card shadow-card-lg overflow-hidden z-30">
              <div className="flex items-center justify-between px-3.5 py-3 border-b border-slate-100">
                <p className="text-sm font-semibold text-slate-800">
                  Notifications
                </p>
                {notificationCount > 0 && (
                  <button
                    type="button"
                    onClick={markAllAsRead}
                    className="flex items-center gap-1 text-xs font-medium text-primary hover:text-primaryHover"
                  >
                    <CheckCheck className="w-3.5 h-3.5" />
                    Mark all as read
                  </button>
                )}
              </div>

              {notifications.length === 0 ? (
                <EmptyState
                  icon={Bell}
                  title="No notifications"
                  description="You're all caught up."
                  className="py-8"
                />
              ) : (
                <div className="max-h-80 overflow-y-auto">
                  {notifications.map((notification) => {
                    const config =
                      NOTIFICATION_ICONS[notification.type] ??
                      NOTIFICATION_ICONS.ingestion;
                    const Icon = config.icon;
                    return (
                      <button
                        key={notification.id}
                        type="button"
                        onClick={() => markAsRead(notification.id)}
                        className={cn(
                          "w-full flex items-start gap-3 px-3.5 py-3 text-left border-b border-slate-50 last:border-b-0 hover:bg-slate-50 transition-colors",
                          !notification.read && "bg-bgBlueTint/40",
                        )}
                      >
                        <span
                          className={cn(
                            "flex items-center justify-center w-8 h-8 rounded-full shrink-0",
                            config.className,
                          )}
                        >
                          <Icon className="w-4 h-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-1.5">
                            <span className="text-sm font-medium text-slate-800 truncate">
                              {notification.title}
                            </span>
                            {!notification.read && (
                              <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
                            )}
                          </span>
                          <span className="block text-xs text-slate-500 mt-0.5">
                            {notification.message}
                          </span>
                          <span className="block text-xs text-slate-400 mt-1">
                            {formatTimeAgo(notification.timestamp)}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

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
