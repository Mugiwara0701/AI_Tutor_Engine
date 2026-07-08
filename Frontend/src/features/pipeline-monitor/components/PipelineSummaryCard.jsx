// src/features/pipeline-monitor/components/PipelineSummaryCard.jsx
// Placeholder for PipelineSummaryCard — implement component/logic here.

// src/features/pipeline-monitor/components/PipelineSummaryCard.jsx

import { useState } from "react";
import { Copy, Check, Cpu, Clock, Layers } from "lucide-react";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import { formatDate } from "../../../utils/formatDate.js";
import { formatDuration } from "../../../utils/formatDuration.js";

export default function PipelineSummaryCard({ pipeline, elapsedMinutes }) {
  const [copied, setCopied] = useState(false);

  const overallPercentage = Math.round(
    (pipeline.completedSteps / pipeline.totalSteps) * 100,
  );

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(pipeline.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable — ignore silently
    }
  };

  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-slate-900">
              {pipeline.name}
            </h2>
            <StatusBadge status={pipeline.status} />
          </div>
          <button
            type="button"
            onClick={handleCopyId}
            className="flex items-center gap-1.5 mt-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            {pipeline.id}
            {copied ? (
              <Check className="w-3 h-3 text-green-600" />
            ) : (
              <Copy className="w-3 h-3" />
            )}
          </button>
        </div>

        <div className="flex gap-6 text-sm">
          <div>
            <p className="text-xs text-slate-400">Started At</p>
            <p className="font-medium text-slate-700">
              {formatDate(pipeline.startedAt)}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Elapsed Time</p>
            <p className="font-medium text-slate-700">
              {formatDuration(elapsedMinutes)}
            </p>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-end justify-between mb-2">
          <span className="text-3xl font-bold text-slate-900">
            {overallPercentage}%
          </span>
          <span className="text-sm text-slate-500">
            {pipeline.completedSteps}/{pipeline.totalSteps} Steps Completed
          </span>
        </div>
        <ProgressBar value={overallPercentage} showPercentage={false} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1 border-t border-slate-50">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-btn bg-blue-50 flex items-center justify-center">
            <Layers className="w-4 h-4 text-primary" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Current Stage</p>
            <p className="text-sm font-medium text-slate-700">
              {pipeline.currentStage}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-btn bg-blue-50 flex items-center justify-center">
            <Clock className="w-4 h-4 text-primary" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Est. Time Left</p>
            <p className="text-sm font-medium text-slate-700">
              {formatDuration(pipeline.estimatedTimeLeftMinutes)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-btn bg-blue-50 flex items-center justify-center">
            <Cpu className="w-4 h-4 text-primary" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Items Processed</p>
            <p className="text-sm font-medium text-slate-700">
              {pipeline.itemsProcessed}/{pipeline.itemsTotal}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-btn bg-green-50 flex items-center justify-center">
            <Check className="w-4 h-4 text-green-600" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Success Rate</p>
            <p className="text-sm font-medium text-slate-700">
              {pipeline.successRate}%
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
