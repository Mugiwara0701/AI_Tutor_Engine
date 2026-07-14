// src/features/ingestion/components/IngestionFilterBar.jsx

import { Filter } from "lucide-react";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import SearchBar from "../../../components/ui/SearchBar.jsx";

export default function IngestionFilterBar({
  filters,
  filterOptions,
  onChange,
  onApply,
}) {
  return (
    <div className="flex flex-wrap items-end gap-3 bg-white border border-slate-100 rounded-card px-4 py-3.5">
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="ingestion-filter-board"
          className="text-xs font-medium text-slate-500"
        >
          Board
        </label>
        <Dropdown
          value={filters.board}
          onChange={(v) => onChange("board", v)}
          options={filterOptions.boardOptions}
          placeholder="All"
          className="w-full sm:w-32"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="ingestion-filter-class"
          className="text-xs font-medium text-slate-500"
        >
          Class
        </label>
        <Dropdown
          value={filters.class}
          onChange={(v) => onChange("class", v)}
          options={filterOptions.classOptions}
          placeholder="All"
          className="w-full sm:w-32"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="ingestion-filter-subject"
          className="text-xs font-medium text-slate-500"
        >
          Subject
        </label>
        <Dropdown
          value={filters.subject}
          onChange={(v) => onChange("subject", v)}
          options={filterOptions.subjectOptions}
          placeholder="All"
          className="w-full sm:w-36"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="ingestion-filter-year"
          className="text-xs font-medium text-slate-500"
        >
          Curriculum Year
        </label>
        <Dropdown
          value={filters.curriculum}
          onChange={(v) => onChange("curriculum", v)}
          options={filterOptions.curriculumYearOptions}
          placeholder="All"
          className="w-full sm:w-36"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="ingestion-filter-status"
          className="text-xs font-medium text-slate-500"
        >
          Status
        </label>
        <Dropdown
          value={filters.status}
          onChange={(v) => onChange("status", v)}
          options={filterOptions.statusOptions}
          placeholder="All"
          className="w-full sm:w-32"
        />
      </div>

      <div className="flex flex-col gap-1.5 flex-1 min-w-[200px]">
        <label
          htmlFor="ingestion-filter-search"
          className="text-xs font-medium text-slate-500"
        >
          Search by book name
        </label>
        <SearchBar
          value={filters.search}
          onChange={(v) => onChange("search", v)}
          placeholder="Search by book name…"
        />
      </div>

      <button
        type="button"
        onClick={onApply}
        className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
      >
        <Filter className="w-4 h-4" />
        Filters
      </button>
    </div>
  );
}
