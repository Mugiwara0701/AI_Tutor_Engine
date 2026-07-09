// src/features/global-search/components/QuickActionsCard.jsx
// Placeholder for QuickActionsCard — implement component/logic here.

// src/features/global-search/components/QuickActionsCard.jsx

import { SlidersHorizontal, Share2, Archive, Bookmark } from "lucide-react";

const ACTIONS = [
  { key: "advanced", label: "Advanced Search", icon: SlidersHorizontal },
  { key: "graph", label: "Search in Learning Graph", icon: Share2 },
  { key: "zip", label: "Search in ZIP Files", icon: Archive },
  { key: "saved", label: "Saved Searches", icon: Bookmark },
];

export default function QuickActionsCard({ onAction }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-1">
      <h3 className="text-sm font-semibold text-slate-800 mb-2">
        Quick Actions
      </h3>

      {ACTIONS.map((action) => (
        <button
          key={action.key}
          type="button"
          onClick={() => onAction?.(action.key)}
          className="flex items-center gap-2.5 px-2 py-2 rounded-btn text-sm text-slate-600 hover:bg-slate-50 hover:text-primary transition-colors text-left"
        >
          <action.icon className="w-4 h-4 text-slate-400" />
          {action.label}
        </button>
      ))}
    </div>
  );
}
