// src/features/global-search/components/ResultsSection.jsx
// Placeholder for ResultsSection — implement component/logic here.

// src/features/global-search/components/ResultsSection.jsx

import ResultRow from "./ResultRow.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";

export default function ResultsSection({
  title,
  icon: Icon,
  iconClassName,
  results,
}) {
  if (!results.length) return null;

  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-50">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-800">
            {title}{" "}
            <span className="text-slate-400 font-normal">
              ({results.length})
            </span>
          </h3>
        </div>
        <a
          href="#"
          className="text-sm font-medium text-primary hover:underline"
        >
          View all {results.length} {title.toLowerCase()} →
        </a>
      </div>

      <div className="divide-y divide-slate-50">
        {results.map((result) => (
          <ResultRow
            key={result.id}
            icon={Icon}
            iconClassName={iconClassName}
            result={result}
          />
        ))}
      </div>
    </div>
  );
}

export function EmptyResultsState() {
  return (
    <div className="bg-white border border-slate-100 rounded-card">
      <EmptyState
        title="No results found"
        description="Try a different search term or adjust your filters."
      />
    </div>
  );
}
