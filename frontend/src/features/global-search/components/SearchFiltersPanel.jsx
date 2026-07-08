// src/features/global-search/components/SearchFiltersPanel.jsx
// Placeholder for SearchFiltersPanel — implement component/logic here.

// src/features/global-search/components/SearchFiltersPanel.jsx

import Dropdown from "../../../components/ui/Dropdown.jsx";

export default function SearchFiltersPanel({
  filters,
  filterOptions,
  onChange,
  onApply,
}) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-800">Search Filters</h3>

      <Dropdown
        label="Class"
        value={filters.class}
        onChange={(v) => onChange("class", v)}
        options={filterOptions.class}
      />
      <Dropdown
        label="Subject"
        value={filters.subject}
        onChange={(v) => onChange("subject", v)}
        options={filterOptions.subject}
      />
      <Dropdown
        label="Book"
        value={filters.book}
        onChange={(v) => onChange("book", v)}
        options={filterOptions.book}
      />
      <Dropdown
        label="Content Type"
        value={filters.contentType}
        onChange={(v) => onChange("contentType", v)}
        options={filterOptions.contentType}
      />
      <Dropdown
        label="Status"
        value={filters.status}
        onChange={(v) => onChange("status", v)}
        options={filterOptions.status}
      />

      <div>
        <p className="text-xs text-slate-500 mb-1.5">Date Modified</p>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(e) => onChange("dateFrom", e.target.value)}
            className="w-full px-2.5 py-2 rounded-btn border border-slate-200 text-xs text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          <span className="text-slate-300 text-xs">–</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(e) => onChange("dateTo", e.target.value)}
            className="w-full px-2.5 py-2 rounded-btn border border-slate-200 text-xs text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>

      <button
        type="button"
        onClick={onApply}
        className="w-full py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
      >
        Apply Filters
      </button>
    </div>
  );
}
