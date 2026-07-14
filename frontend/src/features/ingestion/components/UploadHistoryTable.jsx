// src/features/ingestion/components/UploadHistoryTable.jsx

import { Eye, Download, Trash2, RefreshCcw } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import IngestionStatusBadge from "./IngestionStatusBadge.jsx";
import VersionBadge from "../../../components/ui/VersionBadge.jsx";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";

const PROGRESS_COLOR = {
  Completed: "green",
  "In Progress": "primary",
  Failed: "red",
  Queued: "slate",
};

export default function UploadHistoryTable({
  uploads,
  onSelectUpload,
  selectedIds,
  onSelectionChange,
}) {
  const columns = [
    {
      key: "book",
      label: "Book",
      sortable: true,
      render: (row) => (
        <div className="flex items-center gap-2.5 min-w-0">
          <FileTypeIcon type="zip" size="sm" />
          <span className="font-medium text-slate-800 truncate">
            {row.book}
          </span>
        </div>
      ),
    },
    { key: "board", label: "Board" },
    { key: "class", label: "Class" },
    { key: "subject", label: "Subject" },
    { key: "curriculum", label: "Curriculum" },
    {
      key: "version",
      label: "Version",
      render: (row) => <VersionBadge version={row.version} />,
    },
    {
      key: "uploadedBy",
      label: "Uploaded By",
      render: (row) => (
        <UserAvatar name={row.uploadedBy?.name} size="sm" showDetails />
      ),
    },
    {
      key: "uploadedOn",
      label: "Uploaded On",
      sortable: true,
      render: (row) => (
        <span className="text-slate-500 whitespace-nowrap">
          {row.uploadedOnDisplay}
        </span>
      ),
    },
    {
      key: "currentStage",
      label: "Current Stage",
      render: (row) => (
        <span className="text-slate-500 whitespace-nowrap">
          {row.currentStage}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (row) => <IngestionStatusBadge status={row.status} />,
    },
    {
      key: "progress",
      label: "Progress",
      render: (row) => (
        <ProgressBar
          value={row.progress}
          color={PROGRESS_COLOR[row.status] ?? "primary"}
          className="min-w-[110px]"
        />
      ),
    },
    {
      key: "actions",
      label: "Actions",
      align: "right",
      render: (row) => (
        <div
          onClick={(e) => e.stopPropagation()}
          className="flex items-center justify-end gap-1"
        >
          <button
            type="button"
            onClick={() => onSelectUpload(row.id)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`View ${row.book}`}
          >
            <Eye className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Download ${row.book}`}
          >
            <Download className="w-4 h-4" />
          </button>
          <ActionMenu
            items={[
              {
                label: "View details",
                icon: Eye,
                onClick: () => onSelectUpload(row.id),
              },
              {
                label: "Retry ingestion",
                icon: RefreshCcw,
                onClick: () => {},
              },
              {
                label: "Remove record",
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
    <div>
      <div className="flex items-center justify-between px-1 pb-3">
        <h2 className="text-sm font-semibold text-slate-800">
          Upload History
        </h2>
      </div>
      <DataTable
        columns={columns}
        data={uploads}
        onRowClick={(row) => onSelectUpload(row.id)}
        selectable
        selectedIds={selectedIds}
        onSelectionChange={onSelectionChange}
        pageSize={7}
        emptyTitle="No uploads match your filters"
        emptyDescription="Try adjusting or clearing the filters above."
      />
    </div>
  );
}
