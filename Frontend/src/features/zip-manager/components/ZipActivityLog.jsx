// src/features/zip-manager/components/ZipActivityLog.jsx
// Placeholder for ZipActivityLog — implement component/logic here.

// src/features/zip-manager/components/ZipActivityLog.jsx

import ActivityLogItem from "../../../components/shared/ActivityLogItem.jsx";

export default function ZipActivityLog({ activity }) {
  return (
    <div>
      <p className="text-sm font-semibold text-slate-800 mb-3">Activity Log</p>
      <div className="flex flex-col gap-3">
        {activity.map((entry, i) => (
          <ActivityLogItem
            key={i}
            action={entry.action}
            user={entry.user}
            timestamp={entry.timestamp}
          />
        ))}
      </div>
    </div>
  );
}
