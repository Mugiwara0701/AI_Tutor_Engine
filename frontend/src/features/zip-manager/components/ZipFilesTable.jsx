// src/features/zip-manager/components/ZipFilesTable.jsx
// Placeholder for ZipFilesTable — implement component/logic here.

// src/features/zip-manager/components/ZipFilesTable.jsx

import { Eye, Download, Trash2, Archive } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import { formatBytes } from "../../../utils/formatBytes.js";
import { formatDate } from "../../../utils/formatDate.js";

export default function ZipFilesTable({
  zips,
  onSelectZip,
  selectedIds,
  onSelectionChange,
}) {
  const columns = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (row) => (
        <div className="flex items-center gap-3 min-w-0">
          <FileTypeIcon type="zip" />
          <div className="min-w-0">
            <p className="font-medium text-slate-800 truncate">{row.name}</p>
            <p className="text-xs text-slate-400 truncate">{row.description}</p>
          </div>
        </div>
      ),
    },
    { key: "class", label: "Class", sortable: true },
    {
      key: "chapterTopic",
      label: "Chapter/Topic",
      render: (row) => (
        <span className="text-slate-500">{row.chapterTopic}</span>
      ),
    },
    {
      key: "sizeBytes",
      label: "Size",
      sortable: true,
      render: (row) => formatBytes(row.sizeBytes),
    },
    { key: "filesCount", label: "Files", sortable: true },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "updatedOn",
      label: "Updated On",
      sortable: true,
      render: (row) => (
        <span className="text-slate-500">{formatDate(row.updatedOn)}</span>
      ),
    },
    {
      key: "actions",
      label: "",
      align: "right",
      render: (row) => (
        <div
          onClick={(e) => e.stopPropagation()}
          className="flex items-center justify-end gap-1"
        >
          <button
            type="button"
            onClick={() => onSelectZip(row.id)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Preview ${row.name}`}
          >
            <Eye className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Download ${row.name}`}
          >
            <Download className="w-4 h-4" />
          </button>
          <ActionMenu
            items={[
              {
                label: "Open Details",
                icon: Archive,
                onClick: () => onSelectZip(row.id),
              },
              {
                label: "Delete",
                icon: Trash2,
                danger: true,
                onClick: () => {},
              },
            ]}
          />
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={zips}
      onRowClick={(row) => onSelectZip(row.id)}
      selectable
      selectedIds={selectedIds}
      onSelectionChange={onSelectionChange}
      emptyTitle="No ZIP files match your filters"
      emptyDescription="Try clearing filters to see all ZIP packages."
    />
  );
}
