// src/features/analytics/pages/AnalyticsPage.jsx
// Placeholder for AnalyticsPage — implement component/logic here.

// src/features/analytics/pages/AnalyticsPage.jsx

import { useAnalyticsData } from "../hooks/useAnalyticsData.js";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import MetricsRow from "../components/MetricsRow.jsx";
import ExecutionSuccessDonut from "../components/ExecutionSuccessDonut.jsx";
import ComplexChaptersBarChart from "../components/ComplexChaptersBarChart.jsx";
import ZipUploadTrendsChart from "../components/ZipUploadTrendsChart.jsx";
import PromptVersionsBarChart from "../components/PromptVersionsBarChart.jsx";
import GpuUtilizationChart from "../components/GpuUtilizationChart.jsx";
import StorageUsagePanel from "../components/StorageUsagePanel.jsx";
import TopTopicsTable from "../components/TopTopicsTable.jsx";
import RecentActivityFeed from "../components/RecentActivityFeed.jsx";

export default function AnalyticsPage() {
  const {
    dateRange,
    setDateRange,
    dateRangeOptions,
    metrics,
    executionSuccess,
    complexChapters,
    zipUploadTrends,
    promptVersions,
    gpuUtilization,
    storageUsage,
    topTopics,
    recentActivity,
  } = useAnalyticsData();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Insights into content generation performance and usage.
          </p>
        </div>

        <Dropdown
          value={dateRange}
          onChange={setDateRange}
          options={dateRangeOptions}
          placeholder={dateRange}
          className="w-44"
        />
      </div>

      <MetricsRow metrics={metrics} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <ExecutionSuccessDonut data={executionSuccess} />
        <ComplexChaptersBarChart data={complexChapters} />
        <ZipUploadTrendsChart data={zipUploadTrends} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <PromptVersionsBarChart promptVersions={promptVersions} />
        <GpuUtilizationChart gpuUtilization={gpuUtilization} />
        <StorageUsagePanel storageUsage={storageUsage} />
      </div>

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0">
          <TopTopicsTable topics={topTopics} />
        </div>
        <div className="w-full lg:w-80 shrink-0">
          <RecentActivityFeed activity={recentActivity} />
        </div>
      </div>
    </div>
  );
}
