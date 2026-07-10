// src/features/dashboard/pages/DashboardPage.jsx

import { useAuth } from "../../auth/hooks/useAuth.js";
import { useDashboardData } from "../hooks/useDashboardData.js";
import QuickStatsRow from "../components/QuickStatsRow.jsx";
import RecentActivityFeed from "../components/RecentActivityFeed.jsx";
import StorageOverviewCard from "../components/StorageOverviewCard.jsx";
import WeeklySummaryCard from "../components/WeeklySummaryCard.jsx";
import GettingStartedCard from "../components/GettingStartedCard.jsx";

export default function DashboardPage() {
  const { user } = useAuth();
  const { quickStats, recentActivity, weeklySummary, isNewUser } =
    useDashboardData();

  return (
    <div className="max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">
          Welcome back, {user?.name?.split(" ")[0] ?? "there"} 👋
        </h1>
        <p className="text-slate-500">
          Here's what's happening across your content pipeline today.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        <QuickStatsRow stats={quickStats} />

        {isNewUser && <GettingStartedCard />}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2">
            <RecentActivityFeed activity={recentActivity} />
          </div>
          <div className="flex flex-col gap-6">
            <WeeklySummaryCard summary={weeklySummary} />
            <StorageOverviewCard
              usedGB={quickStats.storageUsedGB}
              totalGB={quickStats.storageTotalGB}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
