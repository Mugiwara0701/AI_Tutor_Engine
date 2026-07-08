// src/features/library/components/ChapterPreviewCard.jsx
// Placeholder for ChapterPreviewCard — implement component/logic here.

// src/features/library/components/ChapterPreviewCard.jsx

import {
  BookOpen,
  Share2,
  Sparkles,
  Layers,
  GitBranch,
  Lightbulb,
} from "lucide-react";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";

export default function ChapterPreviewCard({ chapter }) {
  if (!chapter) {
    return (
      <div className="bg-white border border-slate-100 rounded-card">
        <EmptyState
          title="Select a chapter"
          description="Choose a chapter from the tree or table above to preview it here."
        />
      </div>
    );
  }

  const stats = [
    { label: "Main Topics", value: chapter.mainTopics, icon: Layers },
    { label: "Sub Topics", value: chapter.subTopics, icon: GitBranch },
    { label: "Concepts", value: chapter.concepts, icon: Lightbulb },
  ];

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col md:flex-row gap-5">
      <img
        src={chapter.thumbnail}
        alt={chapter.name}
        className="w-full md:w-48 h-32 object-cover rounded-btn shrink-0"
      />

      <div className="flex-1 min-w-0 flex flex-col gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-base font-semibold text-slate-900 truncate">
              {chapter.name}
            </h3>
            <StatusBadge status={chapter.status} />
          </div>
          <p className="text-xs text-slate-400 mb-1.5">{chapter.breadcrumb}</p>
          <p className="text-sm text-slate-500">{chapter.description}</p>
        </div>

        <div className="flex flex-wrap items-center gap-5">
          {stats.map((stat) => (
            <div key={stat.label} className="flex items-center gap-1.5 text-sm">
              <stat.icon className="w-4 h-4 text-slate-400" />
              <span className="font-medium text-slate-700">{stat.value}</span>
              <span className="text-slate-400">{stat.label}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 mt-1">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <BookOpen className="w-4 h-4" />
            Open Chapter
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            <Share2 className="w-4 h-4" />
            View Learning Graph
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Generate Prompt
          </button>
        </div>
      </div>
    </div>
  );
}
