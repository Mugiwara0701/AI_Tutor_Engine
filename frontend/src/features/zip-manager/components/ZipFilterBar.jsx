// src/features/zip-manager/components/ZipFilterBar.jsx
// Placeholder for ZipFilterBar — implement component/logic here.

// src/features/zip-manager/components/ZipFilterBar.jsx

import { X } from "lucide-react";
import SearchBar from "../../../components/ui/SearchBar.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";

export default function ZipFilterBar({
  filters,
  filterOptions,
  onChange,
  onClear,
}) {
  const hasActiveFilters =
    filters.search ||
    filters.class ||
    filters.subject ||
    filters.chapter ||
    filters.status;

  return (
    <div className="flex flex-wrap items-center gap-3 bg-white border border-slate-100 rounded-card px-4 py-3">
      <SearchBar
        value={filters.search}
        onChange={(v) => onChange("search", v)}
        placeholder="Search ZIPs…"
        className="w-full sm:w-64"
      />
      <Dropdown
        label="Class"
        value={filters.class}
        onChange={(v) => onChange("class", v)}
        options={filterOptions.classOptions}
        className="w-full sm:w-36"
      />
      <Dropdown
        label="Subject"
        value={filters.subject}
        onChange={(v) => onChange("subject", v)}
        options={filterOptions.subjectOptions}
        className="w-full sm:w-40"
      />
      <Dropdown
        label="Chapter"
        value={filters.chapter}
        onChange={(v) => onChange("chapter", v)}
        options={filterOptions.chapterOptions}
        className="w-full sm:w-56"
      />
      <Dropdown
        label="Status"
        value={filters.status}
        onChange={(v) => onChange("status", v)}
        options={filterOptions.statusOptions}
        className="w-full sm:w-36"
      />
      {hasActiveFilters && (
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1.5 px-3 py-2 rounded-btn text-sm font-medium text-slate-500 hover:bg-slate-50 transition-colors ml-auto"
        >
          <X className="w-4 h-4" />
          Clear Filters
        </button>
      )}
    </div>
  );
}
