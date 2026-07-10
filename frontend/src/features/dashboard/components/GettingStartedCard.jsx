// src/features/dashboard/components/GettingStartedCard.jsx

import { useNavigate } from "react-router-dom";
import { Sparkles, Upload, Code2, Activity, Check } from "lucide-react";

const STEPS = [
  {
    key: "upload",
    label: "Upload your first content ZIP",
    icon: Upload,
    path: "/zip-manager",
    done: true,
  },
  {
    key: "prompt",
    label: "Review the default master prompt",
    icon: Code2,
    path: "/prompt-studio",
    done: false,
  },
  {
    key: "pipeline",
    label: "Run your first pipeline",
    icon: Activity,
    path: "/pipeline-monitor",
    done: false,
  },
];

export default function GettingStartedCard() {
  const navigate = useNavigate();
  const completedCount = STEPS.filter((s) => s.done).length;

  return (
    <div className="bg-gradient-to-br from-blue-50 to-white border border-blue-100 rounded-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="w-4 h-4 text-primary" />
        <h3 className="text-sm font-semibold text-slate-900">
          Getting started
        </h3>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        {completedCount} of {STEPS.length} steps complete — finish these to get
        your first pipeline running.
      </p>

      <div className="flex flex-col gap-2">
        {STEPS.map(({ key, label, icon: Icon, path, done }) => (
          <button
            key={key}
            type="button"
            onClick={() => navigate(path)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-btn bg-white border border-slate-100 text-left hover:border-blue-200 transition-colors"
          >
            <div
              className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                done ? "bg-green-500" : "bg-slate-100"
              }`}
            >
              {done ? (
                <Check className="w-3.5 h-3.5 text-white" />
              ) : (
                <Icon className="w-3.5 h-3.5 text-slate-400" />
              )}
            </div>
            <span
              className={`text-sm ${
                done ? "text-slate-400 line-through" : "text-slate-700"
              }`}
            >
              {label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
