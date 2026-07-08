// src/features/global-search/components/SearchTabsFilter.jsx
// Placeholder for SearchTabsFilter — implement component/logic here.

// src/features/global-search/components/SearchTabsFilter.jsx

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

const CORE_TABS = [
  { key: "all", label: "All" },
  { key: "chapters", label: "Chapters" },
  { key: "topics", label: "Topics" },
  { key: "resources", label: "Resources" },
  { key: "prompts", label: "Prompts" },
  { key: "files", label: "Files" },
];

const MORE_TABS = ["Concepts", "Master Prompts", "ZIP Files"];

export default function SearchTabsFilter({ activeTab, onChange, counts }) {
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <div className="flex items-center gap-1 border-b border-slate-100 overflow-x-auto no-scrollbar">
      {CORE_TABS.map((tab) => {
        const isActive = tab.key === activeTab;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors",
              isActive
                ? "border-primary text-primary"
                : "border-transparent text-slate-500 hover:text-slate-700",
            )}
          >
            {tab.label}
            <span className="ml-1.5 text-xs text-slate-400">
              ({counts[tab.key] ?? 0})
            </span>
          </button>
        );
      })}

      <div className="relative ml-auto">
        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          className="flex items-center gap-1 px-3 py-2.5 text-sm font-medium text-slate-500 hover:text-slate-700 transition-colors"
        >
          More
          <ChevronDown className="w-3.5 h-3.5" />
        </button>

        {moreOpen && (
          <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-slate-100 rounded-card shadow-lg py-1 z-20">
            {MORE_TABS.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => setMoreOpen(false)}
                className="w-full text-left px-3.5 py-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
