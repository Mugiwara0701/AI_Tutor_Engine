// src/features/analytics/components/StorageUsagePanel.jsx
// Placeholder for StorageUsagePanel — implement component/logic here.

// src/features/analytics/components/StorageUsagePanel.jsx

import { Link } from "react-router-dom";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import { formatGB } from "../../../utils/formatBytes.js";

export default function StorageUsagePanel({ storageUsage }) {
  const percentage =
    storageUsage.totalGB > 0
      ? (storageUsage.usedGB / storageUsage.totalGB) * 100
      : 0;
  const color =
    percentage > 90 ? "red" : percentage > 70 ? "orange" : "primary";

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-slate-800">Storage Usage</h3>

      <ProgressBar value={percentage} color={color} />

      <p className="text-sm text-slate-600">
        {formatGB(storageUsage.usedGB)} / {formatGB(storageUsage.totalGB)} used
      </p>

      <Link
        to="/storage-explorer"
        className="text-sm font-medium text-primary hover:underline"
      >
        View Storage Explorer →
      </Link>
    </div>
  );
}
