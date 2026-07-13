// src/features/ingestion/components/IngestionPipelineProgress.jsx

import { useNavigate } from "react-router-dom";
import { Check, Activity } from "lucide-react";
import IngestionStatusBadge from "./IngestionStatusBadge.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";
import { cn } from "../../../utils/classNames.js";

function StepIcon({ status, index }) {
  if (status === "Completed") {
    return (
      <span className="w-6 h-6 rounded-full bg-green-500 text-white flex items-center justify-center shrink-0">
        <Check className="w-3.5 h-3.5" strokeWidth={3} />
      </span>
    );
  }
  if (status === "In Progress") {
    return (
      <span className="w-6 h-6 rounded-full border-2 border-primary text-primary bg-white flex items-center justify-center shrink-0">
        <Activity className="w-3 h-3" />
      </span>
    );
  }
  if (status === "Failed") {
    return (
      <span className="w-6 h-6 rounded-full bg-red-500 text-white flex items-center justify-center text-xs font-semibold shrink-0">
        !
      </span>
    );
  }
  return (
    <span className="w-6 h-6 rounded-full bg-slate-100 text-slate-400 text-xs font-semibold flex items-center justify-center shrink-0">
      {index + 1}
    </span>
  );
}

export default function IngestionPipelineProgress({ upload }) {
  const navigate = useNavigate();

  if (!upload) {
    return (
      <div className="bg-white border border-slate-100 rounded-card">
        <EmptyState
          title="No pipeline to show"
          description="Select an upload to see its pipeline progress."
        />
      </div>
    );
  }

  const steps = upload.pipeline ?? [];

  const handleOpenPipelineMonitor = () => {
    // Frontend-only navigation to the existing Pipeline Monitor route.
    navigate("/pipeline-monitor");
  };

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">
          Pipeline Progress
        </h2>
        <span className="text-xs text-slate-400">{upload.book}</span>
      </div>

      <ol className="flex flex-col">
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          return (
            <li key={step.id} className="relative flex gap-3 pb-5 last:pb-0">
              {!isLast && (
                <span
                  className={cn(
                    "absolute left-[11px] top-6 bottom-0 w-px",
                    step.status === "Completed"
                      ? "bg-green-200"
                      : "bg-slate-200",
                  )}
                  aria-hidden="true"
                />
              )}
              <StepIcon status={step.status} index={index} />
              <div className="flex-1 min-w-0 flex items-start justify-between gap-2 -mt-0.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-700 truncate">
                    {step.name}
                  </p>
                  <p className="text-xs text-slate-400">
                    {step.status === "Pending"
                      ? "Waiting to start"
                      : step.status === "In Progress"
                        ? `Extracting… ${step.progress}%`
                        : step.status === "Failed"
                          ? "Step failed"
                          : "Completed"}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <IngestionStatusBadge status={step.status} />
                  {step.status === "In Progress" && (
                    <span className="text-xs font-semibold text-primary">
                      {step.progress}%
                    </span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <button
        type="button"
        onClick={handleOpenPipelineMonitor}
        className="w-full flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
      >
        <Activity className="w-4 h-4" />
        Open in Pipeline Monitor
      </button>
    </div>
  );
}
