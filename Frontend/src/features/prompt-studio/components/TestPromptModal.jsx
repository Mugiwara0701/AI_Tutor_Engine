// src/features/prompt-studio/components/TestPromptModal.jsx

import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";

export default function TestPromptModal({ open, onClose, promptContent }) {
  const [status, setStatus] = useState("idle"); // idle | running | done

  useEffect(() => {
    if (!open) {
      setStatus("idle");
      return;
    }
    setStatus("running");
    const timer = setTimeout(() => setStatus("done"), 1400);
    return () => clearTimeout(timer);
  }, [open]);

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Test Prompt"
      maxWidth="lg"
    >
      <div className="flex flex-col gap-4">
        <div>
          <p className="text-xs font-medium text-slate-400 mb-1.5">
            Prompt sent to model
          </p>
          <pre className="bg-[#1E1E2E] text-slate-300 text-xs font-mono rounded-btn p-3 max-h-40 overflow-auto whitespace-pre-wrap leading-5">
            {promptContent}
          </pre>
        </div>

        <div>
          <p className="text-xs font-medium text-slate-400 mb-1.5">
            Response preview
          </p>
          {status === "running" && (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" />
              Running test generation…
            </div>
          )}
          {status === "done" && (
            <div className="bg-bgBlueTint border border-blue-100 rounded-btn p-3 flex gap-2.5">
              <Sparkles className="w-4 h-4 text-primary shrink-0 mt-0.5" />
              <p className="text-sm text-blue-800">
                Test run completed successfully. Generated 22 slides with
                speaker notes and 8 key concepts covered — matches the expected
                output schema for this prompt version.
              </p>
            </div>
          )}
        </div>
      </div>
    </ModalDialog>
  );
}
