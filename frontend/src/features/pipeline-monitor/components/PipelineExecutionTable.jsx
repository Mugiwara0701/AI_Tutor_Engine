// src/features/pipeline-monitor/components/PipelineExecutionTable.jsx

import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import { formatTimeAgo } from "../../../utils/formatDate.js";

export default function PipelineExecutionTable({ stages = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-50">
        <h3 className="text-sm font-semibold text-slate-800">
          Pipeline Execution Flow
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b border-slate-50">
              <th className="px-5 py-3 font-medium w-10">#</th>
              <th className="px-5 py-3 font-medium">Stage</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium w-48">Progress</th>
              <th className="px-5 py-3 font-medium">Duration</th>
              <th className="px-5 py-3 font-medium">Processed</th>
              <th className="px-5 py-3 font-medium">Last Update</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((stage) => (
              <tr
                key={stage.id}
                className="border-b border-slate-50 last:border-b-0"
              >
                <td className="px-5 py-3 text-slate-400">{stage.id}</td>
                <td className="px-5 py-3">
                  <p className="font-medium text-slate-800">{stage.name}</p>
                  <p className="text-xs text-slate-400">{stage.description}</p>
                </td>
                <td className="px-5 py-3">
                  <StatusBadge status={stage.status} />
                </td>
                <td className="px-5 py-3">
                  <ProgressBar
                    value={stage.progress}
                    size="sm"
                    color={
                      stage.status === "Completed"
                        ? "green"
                        : stage.status === "In Progress"
                          ? "primary"
                          : "slate"
                    }
                  />
                </td>
                <td className="px-5 py-3 text-slate-600">{stage.duration}</td>
                <td className="px-5 py-3 text-slate-600">{stage.processed}</td>
                <td className="px-5 py-3 text-slate-400 text-xs">
                  {stage.lastUpdate ? formatTimeAgo(stage.lastUpdate) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-slate-50">
        <a
          href="#"
          className="text-sm font-medium text-primary hover:underline"
        >
          View Detailed Logs
        </a>
      </div>
    </div>
  );
}
