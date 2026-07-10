// src/features/dashboard/components/DashboardShortcuts.jsx

import { useNavigate } from "react-router-dom";
import { Library, Code2, Activity, ArrowUpRight } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

const SHORTCUTS = [
  {
    key: "library",
    label: "Library",
    description: "Browse classes, subjects & topics",
    icon: Library,
    path: "/library",
    accent: "bg-blue-50 text-primary",
  },
  {
    key: "prompt-studio",
    label: "Prompt Studio",
    description: "Edit & version master prompts",
    icon: Code2,
    path: "/prompt-studio",
    accent: "bg-purple-50 text-purple-600",
  },
  {
    key: "pipeline-monitor",
    label: "Pipeline Monitor",
    description: "Track content generation runs",
    icon: Activity,
    path: "/pipeline-monitor",
    accent: "bg-green-50 text-green-600",
  },
];

export default function DashboardShortcuts() {
  const navigate = useNavigate();

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">Shortcuts</h3>
      <div className="flex flex-col gap-1">
        {SHORTCUTS.map(
          ({ key, label, description, icon: Icon, path, accent }) => (
            <button
              key={key}
              type="button"
              onClick={() => navigate(path)}
              className="group flex items-center gap-3 px-2.5 py-2.5 rounded-btn text-left hover:bg-slate-50 transition-colors"
            >
              <div
                className={cn(
                  "w-9 h-9 rounded-btn flex items-center justify-center shrink-0",
                  accent,
                )}
              >
                <Icon className="w-4.5 h-4.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800">{label}</p>
                <p className="text-xs text-slate-400 truncate">{description}</p>
              </div>
              <ArrowUpRight className="w-4 h-4 text-slate-300 group-hover:text-slate-400 shrink-0" />
            </button>
          ),
        )}
      </div>
    </div>
  );
}
