// src/features/sub-topic-order/components/TipsCard.jsx
// Placeholder for TipsCard — implement component/logic here.

// src/features/sub-topic-order/components/TipsCard.jsx

import { Lightbulb } from "lucide-react";

const TIPS = [
  "Place prerequisite sub topics first so learners build foundational knowledge before moving on.",
  "Group core concepts together to keep related ideas close in the learning path.",
  "Save important-but-non-essential sub topics for later in the sequence.",
  "Use Auto Order to get a sensible starting point, then fine-tune manually.",
];

export default function TipsCard() {
  return (
    <div className="bg-yellow-50 border border-yellow-100 rounded-card p-5">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-4 h-4 text-yellow-600" />
        <p className="text-sm font-semibold text-yellow-800">
          Tips for ordering
        </p>
      </div>
      <ul className="space-y-2">
        {TIPS.map((tip, i) => (
          <li key={i} className="flex gap-2 text-sm text-yellow-800/80">
            <span className="text-yellow-500 mt-0.5">•</span>
            <span>{tip}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
