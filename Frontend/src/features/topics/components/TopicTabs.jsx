// src/features/topics/components/TopicTabs.jsx
// Placeholder for TopicTabs — implement component/logic here.

// src/features/topics/components/TopicTabs.jsx

import { cn } from "../../../utils/classNames.js";

export default function TopicTabs({ tabs, activeTab, onChange }) {
  return (
    <div className="border-b border-slate-100">
      <div className="flex gap-1 overflow-x-auto no-scrollbar">
        {tabs.map((tab) => {
          const isActive = tab === activeTab;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => onChange(tab)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors",
                isActive
                  ? "border-primary text-primary"
                  : "border-transparent text-slate-500 hover:text-slate-700",
              )}
            >
              {tab}
            </button>
          );
        })}
      </div>
    </div>
  );
}
