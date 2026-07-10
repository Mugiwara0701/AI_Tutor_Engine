// src/features/dashboard/hooks/useDashboardData.js

import { useMemo } from "react";
import mockDashboard from "../data/mockDashboard.json";

export function useDashboardData() {
  const quickStats = mockDashboard.quickStats;
  const recentActivity = mockDashboard.recentActivity;
  const weeklySummary = mockDashboard.weeklySummary;
  const isNewUser = mockDashboard.isNewUser;

  const storagePercentage = useMemo(() => {
    const { storageUsedGB, storageTotalGB } = quickStats;
    return storageTotalGB > 0 ? (storageUsedGB / storageTotalGB) * 100 : 0;
  }, [quickStats]);

  return {
    quickStats,
    recentActivity,
    weeklySummary,
    isNewUser,
    storagePercentage,
  };
}
