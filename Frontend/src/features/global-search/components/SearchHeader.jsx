// src/features/global-search/components/SearchHeader.jsx
// Placeholder for SearchHeader — implement component/logic here.

// src/features/global-search/components/SearchHeader.jsx

import { X } from "lucide-react";
import SearchBar from "../../../components/ui/SearchBar.jsx";

export default function SearchHeader({ query, onChange }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Global Search</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Search across chapters, topics, prompts, and files in one place.
        </p>
      </div>

      <div className="relative w-full max-w-xl">
        <SearchBar
          value={query}
          onChange={onChange}
          placeholder="Search anything…"
          className="w-full"
        />
        {query && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {query && (
        <p className="text-sm text-slate-400">
          Showing results for{" "}
          <span className="font-medium text-slate-600">"{query}"</span>
        </p>
      )}
    </div>
  );
}
