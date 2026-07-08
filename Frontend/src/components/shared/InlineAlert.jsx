// src/components/shared/InlineAlert.jsx
//
// Lightweight, self-dismissing success/error banner for frontend-only flows
// (form submissions with no backend to confirm against).

import { useEffect } from "react";
import { CheckCircle2, AlertCircle, X } from "lucide-react";
import { cn } from "../../utils/classNames.js";

export default function InlineAlert({ type = "success", message, onDismiss }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => onDismiss?.(), 4000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  if (!message) return null;

  const isSuccess = type === "success";
  const Icon = isSuccess ? CheckCircle2 : AlertCircle;

  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-2.5 px-4 py-2.5 rounded-btn border text-sm font-medium",
        isSuccess
          ? "bg-green-50 border-green-100 text-green-700"
          : "bg-red-50 border-red-100 text-red-700",
      )}
    >
      <Icon className="w-4 h-4 shrink-0" />
      <span className="flex-1">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="p-0.5 rounded hover:bg-black/5 transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
