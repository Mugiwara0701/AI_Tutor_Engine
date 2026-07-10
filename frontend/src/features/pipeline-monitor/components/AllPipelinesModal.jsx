// src/features/pipeline-monitor/components/AllPipelinesModal.jsx

import { Play, Pause } from "lucide-react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";

export default function AllPipelinesModal({
  open,
  onClose,
  pipelines,
  onToggle,
}) {
  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="All Pipelines"
      maxWidth="xl"
    >
      <div className="flex flex-col divide-y divide-slate-100">
        {pipelines.map((pipeline) => {
          const isActive = pipeline.status === "Active";
          return (
            <div
              key={pipeline.id}
              className="flex items-center justify-between gap-4 py-3.5 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">
                  {pipeline.name}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {pipeline.currentStage} · {pipeline.progress}% complete
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <StatusBadge status={pipeline.status} />
                <button
                  type="button"
                  onClick={() => onToggle(pipeline.id)}
                  className={
                    isActive
                      ? "flex items-center gap-1.5 px-3 py-1.5 rounded-btn border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
                      : "flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-primary text-white text-xs font-medium hover:bg-blue-700 transition-colors"
                  }
                >
                  {isActive ? (
                    <Pause className="w-3.5 h-3.5" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  {isActive ? "Pause" : "Start"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </ModalDialog>
  );
}
