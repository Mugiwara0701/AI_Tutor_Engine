// src/features/topics/components/TopicHeader.jsx

import { Calendar, Clock, Flag } from "lucide-react";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import { formatDate } from "../../../utils/formatDate.js";
import { formatDuration } from "../../../utils/formatDuration.js";
import { cn } from "../../../utils/classNames.js";

const DIFFICULTY_STYLES = {
  easy: "bg-green-50 text-green-600",
  medium: "bg-amber-50 text-amber-600",
  hard: "bg-red-50 text-red-600",
};

const IMPORTANCE_STYLES = {
  low: "bg-slate-100 text-slate-500",
  medium: "bg-blue-50 text-primary",
  high: "bg-purple-50 text-purple-600",
};

export default function TopicHeader({ topic }) {
  if (!topic) return null;

  const difficultyStyle =
    DIFFICULTY_STYLES[topic.difficulty?.toLowerCase()] ??
    "bg-slate-100 text-slate-500";
  const importanceStyle =
    IMPORTANCE_STYLES[topic.importance?.toLowerCase()] ??
    "bg-slate-100 text-slate-500";

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-4">
      <div>
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-bold text-slate-900">{topic.title}</h1>
          <StatusBadge status={topic.status} />
          <span
            className={cn(
              "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium",
              difficultyStyle,
            )}
          >
            {topic.difficulty}
          </span>
        </div>
        <p className="text-sm text-slate-500 mt-2 max-w-3xl">
          {topic.description}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-5 text-sm text-slate-500 border-t border-slate-100 pt-4">
        <span className="flex items-center gap-1.5">
          <Calendar className="w-4 h-4 text-slate-400" />
          Last Updated:{" "}
          <span className="text-slate-700 font-medium">
            {formatDate(topic.lastUpdated)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <Clock className="w-4 h-4 text-slate-400" />
          Learning Time:{" "}
          <span className="text-slate-700 font-medium">
            {formatDuration(topic.learningTimeMinutes)}
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          <Flag className="w-4 h-4 text-slate-400" />
          Importance:{" "}
          <span
            className={cn(
              "px-2 py-0.5 rounded-full text-xs font-medium",
              importanceStyle,
            )}
          >
            {topic.importance}
          </span>
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {topic.statusChips?.map((chip) => (
          <span
            key={chip.label}
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
              chip.done
                ? "bg-green-50 text-green-600"
                : "bg-slate-100 text-slate-500",
            )}
          >
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                chip.done ? "bg-green-500" : "bg-slate-400",
              )}
            />
            {chip.label}
          </span>
        ))}
      </div>
    </div>
  );
}
