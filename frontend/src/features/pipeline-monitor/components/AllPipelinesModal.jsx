// src/features/pipeline-monitor/components/AllPipelinesModal.jsx

import { useEffect, useState } from "react";
import { Play, Pause } from "lucide-react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";

export default function AllPipelinesModal({
  open,
  onClose,
  pipelines,
  onToggle,
}) {
  const [selectedId, setSelectedId] = useState(pipelines[0]?.id ?? "");

  // Keep the selected pipeline valid if the list changes while open,
  // and default to the first pipeline each time the modal is reopened.
  useEffect(() => {
    if (open) {
      setSelectedId(pipelines[0]?.id ?? "");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected =
    pipelines.find((p) => p.id === selectedId) ?? pipelines[0] ?? null;

  if (!selected) return null;

  const isActive = selected.status === "Active";

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Pipeline Control"
      maxWidth="md"
    >
      <div className="flex flex-col gap-4">
        <div>
          <label
            htmlFor="pipeline-select"
            className="block text-xs font-medium text-slate-500 mb-1.5"
          >
            Select Pipeline
          </label>
          <select
            id="pipeline-select"
            value={selected.id}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full px-3 py-2.5 rounded-btn border border-slate-200 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          >
            {pipelines.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>
                {pipeline.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between gap-4 px-4 py-3.5 rounded-btn bg-slate-50 border border-slate-100">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate">
              {selected.name}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {selected.currentStage} · {selected.progress}% complete
            </p>
          </div>
          <StatusBadge status={selected.status} />
        </div>

        <button
          type="button"
          onClick={() => onToggle(selected.id)}
          className={
            isActive
              ? "flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              : "flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          }
        >
          {isActive ? (
            <Pause className="w-4 h-4" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {isActive ? "Pause Pipeline" : "Start Pipeline"}
        </button>
      </div>
    </ModalDialog>
  );
}
