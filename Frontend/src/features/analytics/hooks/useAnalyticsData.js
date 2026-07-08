// src/features/analytics/hooks/useAnalyticsData.js
// Placeholder for useAnalyticsData — implement component/logic here.

// src/features/analytics/hooks/useAnalyticsData.js

import { useState } from "react";
import mockAnalytics from "../data/mockAnalytics.json";

export function useAnalyticsData() {
  const [dateRange, setDateRange] = useState(mockAnalytics.dateRangeOptions[0]);

  return {
    dateRange,
    setDateRange,
    dateRangeOptions: mockAnalytics.dateRangeOptions,
    metrics: mockAnalytics.metrics,
    executionSuccess: mockAnalytics.executionSuccess,
    complexChapters: mockAnalytics.complexChapters,
    zipUploadTrends: mockAnalytics.zipUploadTrends,
    promptVersions: mockAnalytics.promptVersions,
    gpuUtilization: mockAnalytics.gpuUtilization,
    storageUsage: mockAnalytics.storageUsage,
    topTopics: mockAnalytics.topTopics,
    recentActivity: mockAnalytics.recentActivity,
  };
}
