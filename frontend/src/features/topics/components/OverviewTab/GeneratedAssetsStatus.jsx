// src/features/topics/components/OverviewTab/GeneratedAssetsStatus.jsx

import StatusBadge from "../../../../components/ui/StatusBadge.jsx";
import VersionBadge from "../../../../components/ui/VersionBadge.jsx";
import { formatTimeAgo } from "../../../../utils/formatDate.js";

export default function GeneratedAssetsStatus({ assets = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">
        Generated Assets Status
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {assets.map((asset) => (
          <div
            key={asset.key}
            className="flex flex-col gap-1.5 p-3 rounded-btn border border-slate-100"
          >
            <span className="text-xs font-medium text-slate-500">
              {asset.label}
            </span>
            <StatusBadge status={asset.status} />
            <div className="flex items-center justify-between text-xs text-slate-400 mt-1">
              {asset.version ? (
                <VersionBadge version={asset.version} />
              ) : (
                <span>—</span>
              )}
              <span>
                {asset.updatedAt ? formatTimeAgo(asset.updatedAt) : "—"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
