// src/features/prompt-studio/components/VersionHistoryTable.jsx
// Placeholder for VersionHistoryTable — implement component/logic here.

// src/features/prompt-studio/components/VersionHistoryTable.jsx

import { Eye, RotateCcw } from "lucide-react";
import VersionBadge from "../../../components/ui/VersionBadge.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import { formatDate } from "../../../utils/formatDate.js";
import { cn } from "../../../utils/classNames.js";

export default function VersionHistoryTable({
  versions,
  activeVersion,
  onView,
  onRevert,
}) {
  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100">
        <p className="text-sm font-semibold text-slate-800">Version History</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-medium text-slate-400 uppercase tracking-wide border-b border-slate-100">
              <th className="py-2.5 px-4">Version</th>
              <th className="py-2.5 px-4">Updated On</th>
              <th className="py-2.5 px-4">Updated By</th>
              <th className="py-2.5 px-4">Changes</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr
                key={v.version}
                className={cn(
                  "border-b border-slate-100 last:border-b-0",
                  activeVersion?.version === v.version && "bg-bgBlueTint/40",
                )}
              >
                <td className="py-3 px-4">
                  <button
                    type="button"
                    onClick={() => onView(v)}
                    className="hover:opacity-80 transition-opacity"
                  >
                    <VersionBadge version={v.version} isLatest={v.isLatest} />
                  </button>
                </td>
                <td className="py-3 px-4 text-slate-500">
                  {formatDate(v.updatedOn)}
                </td>
                <td className="py-3 px-4">
                  <UserAvatar name={v.updatedBy?.name} size="sm" showDetails />
                </td>
                <td className="py-3 px-4 text-slate-600 max-w-xs truncate">
                  {v.changes}
                </td>
                <td className="py-3 px-4">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => onView(v)}
                      className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                      aria-label={`View ${v.version}`}
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onRevert(v)}
                      className="p-1.5 rounded-btn text-slate-400 hover:text-primary hover:bg-bgBlueTint transition-colors"
                      aria-label={`Revert to ${v.version}`}
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
