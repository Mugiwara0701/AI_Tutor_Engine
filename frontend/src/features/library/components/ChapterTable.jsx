// src/features/library/components/ChapterTable.jsx
// Placeholder for ChapterTable — implement component/logic here.

// src/features/library/components/ChapterTable.jsx

import { BookOpen, Share2, Sparkles, Trash2 } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import { formatTimeAgo } from "../../../utils/formatDate.js";

export default function ChapterTable({
  chapters,
  selectedChapterId,
  onSelectChapter,
}) {
  const columns = [
    {
      key: "name",
      label: "Chapter/Topic",
      sortable: true,
      render: (row) => (
        <div className="min-w-0">
          <p className="font-medium text-slate-800 truncate">{row.name}</p>
          <p className="text-xs text-slate-400 truncate">{row.breadcrumb}</p>
        </div>
      ),
    },
    { key: "mainTopics", label: "Main Topics", sortable: true },
    { key: "subTopics", label: "Sub Topics", sortable: true },
    { key: "concepts", label: "Concepts", sortable: true },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "updatedAt",
      label: "Updated",
      sortable: true,
      render: (row) => (
        <span className="text-slate-500">{formatTimeAgo(row.updatedAt)}</span>
      ),
    },
    {
      key: "actions",
      label: "",
      align: "right",
      render: (row) => (
        <div onClick={(e) => e.stopPropagation()}>
          <ActionMenu
            items={[
              {
                label: "Open Chapter",
                icon: BookOpen,
                onClick: () => onSelectChapter(row.id),
              },
              { label: "View Learning Graph", icon: Share2, onClick: () => {} },
              { label: "Generate Prompt", icon: Sparkles, onClick: () => {} },
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
      data={chapters}
      onRowClick={(row) => onSelectChapter(row.id)}
      emptyTitle="No chapters match your filters"
      emptyDescription="Try clearing filters to see all chapters."
    />
  );
}
