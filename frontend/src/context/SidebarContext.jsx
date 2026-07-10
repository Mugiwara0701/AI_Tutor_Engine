// src/context/SidebarContext.jsx

import { createContext, useCallback, useMemo, useState } from "react";

export const SidebarContext = createContext(null);

export function SidebarProvider({ children }) {
  const [expandedGroups, setExpandedGroups] = useState({ library: true });
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  const toggleGroup = useCallback((key) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((prev) => !prev);
  }, []);

  const openMobileSidebar = useCallback(() => setIsMobileOpen(true), []);
  const closeMobileSidebar = useCallback(() => setIsMobileOpen(false), []);
  const toggleMobileSidebar = useCallback(
    () => setIsMobileOpen((prev) => !prev),
    [],
  );

  const value = useMemo(
    () => ({
      expandedGroups,
      toggleGroup,
      isCollapsed,
      toggleCollapsed,
      isMobileOpen,
      openMobileSidebar,
      closeMobileSidebar,
      toggleMobileSidebar,
    }),
    [
      expandedGroups,
      toggleGroup,
      isCollapsed,
      toggleCollapsed,
      isMobileOpen,
      openMobileSidebar,
      closeMobileSidebar,
      toggleMobileSidebar,
    ],
  );

  return (
    <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
  );
}
