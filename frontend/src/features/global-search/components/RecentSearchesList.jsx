// src/features/global-search/components/RecentSearchesList.jsx

import { Clock, X } from "lucide-react";
import { formatDate } from "../../../utils/formatDate.js";

export default function RecentSearchesList({ searches, onSelect, onRemove }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-slate-800">Recent Searches</h3>

      <div className="flex flex-col gap-1">
        {searches.map((search) => (
          <div key={search.id} className="flex items-center gap-2 group py-1">
            <Clock className="w-3.5 h-3.5 text-slate-300 shrink-0" />
            <button
              type="button"
              onClick={() => onSelect(search.query)}
              className="flex-1 min-w-0 text-left text-sm text-slate-600 hover:text-primary truncate transition-colors"
            >
              {search.query}
            </button>
            <span className="text-xs text-slate-300 shrink-0">
              {formatDate(search.date)}
            </span>
            <button
              type="button"
              onClick={() => onRemove(search.id)}
              aria-label="Remove search"
              className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-slate-500 transition-opacity shrink-0"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      <a href="#" className="text-sm font-medium text-primary hover:underline">
        View All History →
      </a>
    </div>
  );
}
