// src/features/storage-explorer/components/StorageStatsBar.jsx
// Placeholder for StorageStatsBar — implement component/logic here.

// src/features/storage-explorer/components/StorageStatsBar.jsx

import {
  Files,
  FolderTree as FolderTreeIcon,
  Database,
  Layers,
  Clock,
} from "lucide-react";
import { formatBytes } from "../../../utils/formatBytes.js";
import { formatTimeAgo } from "../../../utils/formatDate.js";

export default function StorageStatsBar({ stats }) {
  const items = [
    { icon: Files, label: "Total Files", value: stats.totalFiles },
    { icon: FolderTreeIcon, label: "Total Folders", value: stats.totalFolders },
    {
      icon: Database,
      label: "Total Size",
      value: formatBytes(stats.totalSizeBytes),
    },
    { icon: Layers, label: "File Types", value: stats.fileTypes },
    {
      icon: Clock,
      label: "Last Modified",
      value: stats.lastModified ? formatTimeAgo(stats.lastModified) : "—",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="bg-white border border-slate-100 rounded-card p-4 flex items-center gap-3"
        >
          <div className="w-8 h-8 rounded-btn bg-blue-50 flex items-center justify-center shrink-0">
            <item.icon className="w-4 h-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-slate-400">{item.label}</p>
            <p className="text-sm font-semibold text-slate-800 truncate">
              {item.value}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
