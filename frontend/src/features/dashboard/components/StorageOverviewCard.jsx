// src/features/dashboard/components/StorageOverviewCard.jsx

import { useNavigate } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import StorageUsageBar from "../../../components/shared/StorageUsageBar.jsx";

export default function StorageOverviewCard({ usedGB, totalGB }) {
  const navigate = useNavigate();
  const remainingGB = Math.max(totalGB - usedGB, 0);

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900">Storage</h3>
        <button
          type="button"
          onClick={() => navigate("/storage-explorer")}
          className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Explorer
          <ArrowUpRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <StorageUsageBar usedGB={usedGB} totalGB={totalGB} />

      <p className="text-xs text-slate-400 mt-3">
        {remainingGB.toFixed(1)} GB free across all libraries
      </p>
    </div>
  );
}
