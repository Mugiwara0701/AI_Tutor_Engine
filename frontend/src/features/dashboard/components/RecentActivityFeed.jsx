// src/features/dashboard/components/RecentActivityFeed.jsx

import { History } from "lucide-react";
import ActivityLogItem from "../../../components/shared/ActivityLogItem.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";

export default function RecentActivityFeed({ activity = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900">
          Recent Activity
        </h3>
        {activity.length > 0 && (
          <span className="text-xs font-medium text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full">
            {activity.length} updates
          </span>
        )}
      </div>

      {activity.length === 0 ? (
        <EmptyState
          icon={History}
          title="No activity yet"
          description="Actions across your pipelines and content will show up here."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {activity.map((item) => (
            <ActivityLogItem
              key={item.id}
              action={item.action}
              description={item.description}
              user={item.user}
              timestamp={item.timestamp}
              color={item.color}
            />
          ))}
        </div>
      )}
    </div>
  );
}
