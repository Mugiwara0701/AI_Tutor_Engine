// src/features/zip-manager/components/TopicZipUploadTable.jsx

import { useRef } from "react";
import { Eye, Download, RefreshCw, Trash2, FileArchive } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import { formatDate } from "../../../utils/formatDate.js";

export default function TopicZipUploadTable({
  uploads,
  onView,
  onDownload,
  onReplace,
  onDelete,
}) {
  const replaceInputRef = useRef(null);
  const replaceTargetId = useRef(null);

  const triggerReplace = (id) => {
    replaceTargetId.current = id;
    replaceInputRef.current?.click();
  };

  const handleReplaceFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file && replaceTargetId.current) {
      onReplace(replaceTargetId.current, file.name);
    }
    e.target.value = "";
    replaceTargetId.current = null;
  };

  const columns = [
    { key: "class", label: "Class", sortable: true },
    { key: "subject", label: "Subject", sortable: true },
    {
      key: "chapter",
      label: "Chapter",
      render: (row) => <span className="text-slate-500">{row.chapter}</span>,
    },
    { key: "topicName", label: "Topic Name", sortable: true },
    {
      key: "fileName",
      label: "File Name",
      render: (row) => (
        <div className="flex items-center gap-2 min-w-0">
          <FileArchive className="w-3.5 h-3.5 text-primary shrink-0" />
          <span className="truncate">{row.fileName}</span>
        </div>
      ),
    },
    {
      key: "uploadDate",
      label: "Upload Date",
      sortable: true,
      render: (row) => (
        <span className="text-slate-500">{formatDate(row.uploadDate)}</span>
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
            onClick={() => onView(row)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`View ${row.topicName}`}
          >
            <Eye className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => onDownload(row)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Download ${row.fileName}`}
          >
            <Download className="w-4 h-4" />
          </button>
          <ActionMenu
            items={[
              {
                label: "Replace ZIP",
                icon: RefreshCw,
                onClick: () => triggerReplace(row.id),
              },
              {
                label: "Delete",
                icon: Trash2,
                danger: true,
                onClick: () => onDelete(row.id),
              },
            ]}
          />
        </div>
      ),
    },
  ];

  return (
    <>
      <input
        ref={replaceInputRef}
        type="file"
        accept=".zip"
        onChange={handleReplaceFileChange}
        className="hidden"
      />
      <DataTable
        columns={columns}
        data={uploads}
        emptyTitle="No topic-wise ZIPs uploaded yet"
        emptyDescription="Click “Upload ZIP” to add the first topic package."
      />
    </>
  );
}
