// src/features/sub-topic-order/components/RelationBadge.jsx
// Placeholder for RelationBadge — implement component/logic here.

// src/features/sub-topic-order/components/RelationBadge.jsx

import { cn } from "../../../utils/classNames.js";

const STYLES = {
  Prerequisite: "bg-blue-50 text-blue-600",
  "Core Concept": "bg-green-50 text-green-600",
  Important: "bg-orange-50 text-orange-600",
};

export default function RelationBadge({ relation }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap",
        STYLES[relation] ?? "bg-slate-100 text-slate-500",
      )}
    >
      {relation}
    </span>
  );
}
