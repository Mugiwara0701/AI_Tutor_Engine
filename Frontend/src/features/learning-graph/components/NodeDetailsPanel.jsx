// src/features/learning-graph/components/NodeDetailsPanel.jsx
// Placeholder for NodeDetailsPanel — implement component/logic here.

// src/features/learning-graph/components/NodeDetailsPanel.jsx

import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import { formatDuration } from "../../../utils/formatDuration.js";
import { cn } from "../../../utils/classNames.js";

const TYPE_BADGE_STYLES = {
  mainTopic: "bg-green-50 text-green-600",
  subTopic: "bg-blue-50 text-primary",
  concept: "bg-purple-50 text-purple-600",
};

const TYPE_LABELS = {
  mainTopic: "Main Topic",
  subTopic: "Sub Topic",
  concept: "Concept",
};

function masteryColorKey(mastery) {
  if (mastery >= 80) return "green";
  if (mastery >= 60) return "primary";
  if (mastery >= 40) return "orange";
  return "red";
}

export default function NodeDetailsPanel({ node }) {
  if (!node) {
    return (
      <div className="bg-white border border-slate-100 rounded-card p-4 text-sm text-slate-400">
        Select a node to view details.
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{node.label}</h3>
        <span
          className={cn(
            "px-2 py-0.5 rounded-full text-xs font-medium shrink-0",
            TYPE_BADGE_STYLES[node.type],
          )}
        >
          {TYPE_LABELS[node.type]}
        </span>
      </div>

      <p className="text-sm text-slate-500">{node.description}</p>

      <div className="flex items-center justify-between text-sm text-slate-500 border-t border-slate-100 pt-3">
        <span>Total Concepts</span>
        <span className="font-medium text-slate-700">{node.totalConcepts}</span>
      </div>
      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>Est. Learning Time</span>
        <span className="font-medium text-slate-700">
          {formatDuration(node.learningTimeMinutes)}
        </span>
      </div>

      <div className="pt-1">
        <ProgressBar
          value={node.mastery}
          label="Your Mastery"
          color={masteryColorKey(node.mastery)}
        />
      </div>
    </div>
  );
}
