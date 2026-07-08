// src/context/SidebarContext.jsx
// Placeholder for SidebarContext — implement component/logic here.

import { createContext, useCallback, useMemo, useState } from "react";

export const SidebarContext = createContext(null);

export function SidebarProvider({ children }) {
  const [expandedGroups, setExpandedGroups] = useState({ library: true });
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleGroup = useCallback((key) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const toggleCollapsed = useCallback(() => {
    setIsCollapsed((prev) => !prev);
  }, []);

  const value = useMemo(
    () => ({ expandedGroups, toggleGroup, isCollapsed, toggleCollapsed }),
    [expandedGroups, toggleGroup, isCollapsed, toggleCollapsed],
  );

  return (
    <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
  );
}
