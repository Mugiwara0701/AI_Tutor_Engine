// src/features/learning-graph/components/LearningPathStrip.jsx

import { useState } from "react";
import { Maximize2 } from "lucide-react";
import { cn } from "../../../utils/classNames.js";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";

const TYPE_DOT_STYLES = {
  mainTopic: "bg-green-500",
  subTopic: "bg-blue-600",
  concept: "bg-purple-500",
};

export default function LearningPathStrip({ path = [] }) {
  const [isFullPathOpen, setIsFullPathOpen] = useState(false);

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          Learning Path Suggestion
        </h3>
        <button
          type="button"
          onClick={() => setIsFullPathOpen(true)}
          className="flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
        >
          <Maximize2 className="w-3.5 h-3.5" />
          View Full Path
        </button>
      </div>

      <ModalDialog
        open={isFullPathOpen}
        onClose={() => setIsFullPathOpen(false)}
        title="Learning Path Suggestion"
        maxWidth="md"
      >
        <div className="flex flex-col">
          {path.map((step, i) => (
            <div key={step.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "w-3 h-3 rounded-full shrink-0 mt-1.5",
                    TYPE_DOT_STYLES[step.type] ?? TYPE_DOT_STYLES.concept,
                  )}
                />
                {i < path.length - 1 && (
                  <span className="w-px flex-1 bg-slate-200 my-1" />
                )}
              </div>
              <div className="pb-5">
                <p className="text-sm font-medium text-slate-900">
                  {step.label}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Step {i + 1} of {path.length}
                </p>
              </div>
            </div>
          ))}
        </div>
      </ModalDialog>
    </div>
  );
}
