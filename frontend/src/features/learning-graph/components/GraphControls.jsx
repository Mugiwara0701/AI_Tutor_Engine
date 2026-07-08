// src/features/learning-graph/components/GraphControls.jsx
// Placeholder for GraphControls — implement component/logic here.

// src/features/learning-graph/components/GraphControls.jsx

import { useReactFlow, useViewport } from "reactflow";
import { Minus, Plus, Maximize2, Filter, Download } from "lucide-react";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import Checkbox from "../../../components/ui/Checkbox.jsx";

export default function GraphControls({
  filterOptions,
  filters,
  onFilterChange,
  showMastery,
  onToggleMastery,
}) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const { zoom } = useViewport();

  return (
    <div className="bg-white border border-slate-100 rounded-card p-3.5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Dropdown
          label="Class"
          value={filters.classValue}
          onChange={(v) => onFilterChange("classValue", v)}
          options={filterOptions.classes}
        />
        <Dropdown
          label="Subject"
          value={filters.subjectValue}
          onChange={(v) => onFilterChange("subjectValue", v)}
          options={filterOptions.subjects}
        />
        <Dropdown
          label="Book"
          value={filters.bookValue}
          onChange={(v) => onFilterChange("bookValue", v)}
          options={filterOptions.books}
        />
        <Dropdown
          label="Chapter"
          value={filters.chapterValue}
          onChange={(v) => onFilterChange("chapterValue", v)}
          options={filterOptions.chapters}
        />
        <Checkbox
          checked={showMastery}
          onChange={onToggleMastery}
          label="Show Mastery"
        />
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 border border-slate-200 rounded-btn p-1">
          <button
            type="button"
            onClick={() => zoomOut()}
            className="p-1.5 rounded hover:bg-slate-100 transition-colors"
            aria-label="Zoom out"
          >
            <Minus className="w-3.5 h-3.5 text-slate-500" />
          </button>
          <span className="text-xs font-medium text-slate-600 w-10 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => zoomIn()}
            className="p-1.5 rounded hover:bg-slate-100 transition-colors"
            aria-label="Zoom in"
          >
            <Plus className="w-3.5 h-3.5 text-slate-500" />
          </button>
        </div>

        <button
          type="button"
          onClick={() => fitView()}
          className="p-2 rounded-btn border border-slate-200 hover:bg-slate-50 transition-colors"
          aria-label="Fit view"
          title="Fit to view"
        >
          <Maximize2 className="w-4 h-4 text-slate-500" />
        </button>
        <button
          type="button"
          className="p-2 rounded-btn border border-slate-200 hover:bg-slate-50 transition-colors"
          aria-label="Filter"
        >
          <Filter className="w-4 h-4 text-slate-500" />
        </button>
        <button
          type="button"
          className="p-2 rounded-btn border border-slate-200 hover:bg-slate-50 transition-colors"
          aria-label="Download"
        >
          <Download className="w-4 h-4 text-slate-500" />
        </button>
      </div>
    </div>
  );
}
