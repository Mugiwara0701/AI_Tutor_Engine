// src/features/storage-explorer/components/FileBrowserTable.jsx
// Placeholder for FileBrowserTable — implement component/logic here.

// src/features/storage-explorer/components/FileBrowserTable.jsx

import { Download, Eye, Trash2 } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import { formatBytes } from "../../../utils/formatBytes.js";
import { formatTimeAgo } from "../../../utils/formatDate.js";

const PAGE_SIZE_OPTIONS = ["10", "25", "50"];

export default function FileBrowserTable({
  files,
  selectedIds,
  onSelectionChange,
  pageSize,
  onPageSizeChange,
}) {
  const columns = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (file) => (
        <div className="flex items-center gap-2.5">
          <FileTypeIcon type={file.type} size="sm" />
          <span className="font-medium text-slate-800 truncate">
            {file.name}
          </span>
        </div>
      ),
    },
    {
      key: "type",
      label: "Type",
      sortable: true,
      render: (file) => (
        <span className="uppercase text-xs text-slate-500">{file.type}</span>
      ),
    },
    {
      key: "sizeBytes",
      label: "Size",
      sortable: true,
      render: (file) => formatBytes(file.sizeBytes),
    },
    {
      key: "modified",
      label: "Modified",
      sortable: true,
      render: (file) => formatTimeAgo(file.modified),
    },
    {
      key: "modifiedBy",
      label: "Modified By",
      render: (file) => file.modifiedBy,
    },
    {
      key: "actions",
      label: "",
      render: (file) => (
        <ActionMenu
          items={[
            { label: "Preview", icon: Eye, onClick: () => {} },
            { label: "Download", icon: Download, onClick: () => {} },
            {
              label: "Delete",
              icon: Trash2,
              danger: true,
              onClick: () => {},
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-end">
        <Dropdown
          label="Rows"
          value={String(pageSize)}
          onChange={(v) => onPageSizeChange(Number(v))}
          options={PAGE_SIZE_OPTIONS}
          placeholder={String(pageSize)}
          className="w-32"
        />
      </div>

      <DataTable
        key={pageSize}
        columns={columns}
        data={files}
        selectable
        selectedIds={selectedIds}
        onSelectionChange={onSelectionChange}
        pageSize={pageSize}
        emptyTitle="No files in this folder"
        emptyDescription="Upload files or select a different folder from the tree."
      />
    </div>
  );
}
