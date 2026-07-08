// src/features/analytics/components/RecentActivityFeed.jsx
// Placeholder for RecentActivityFeed — implement component/logic here.

// src/features/analytics/components/RecentActivityFeed.jsx

import ActivityLogItem from "../../../components/shared/ActivityLogItem.jsx";

export default function RecentActivityFeed({ activity = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5">
      <h3 className="text-sm font-semibold text-slate-800 mb-4">
        Recent Activity
      </h3>

      <div className="flex flex-col gap-3">
        {activity.map((entry) => (
          <ActivityLogItem
            key={entry.id}
            action={entry.action}
            timestamp={entry.timestamp}
            color={entry.color}
          />
        ))}
      </div>
    </div>
  );
}
