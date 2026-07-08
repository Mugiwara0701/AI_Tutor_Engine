// src/components/ui/DataTable/TablePagination.jsx
// Placeholder for TablePagination — implement component/logic here.

// src/components/ui/DataTable/TablePagination.jsx

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

export default function TablePagination({
  page,
  pageCount,
  totalItems,
  pageSize,
  onPageChange,
}) {
  if (pageCount <= 1) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalItems);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 text-sm">
      <span className="text-slate-500">
        Showing{" "}
        <span className="font-medium text-slate-700">
          {start}–{end}
        </span>{" "}
        of <span className="font-medium text-slate-700">{totalItems}</span>
      </span>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className={cn(
            "p-1.5 rounded-btn transition-colors",
            page === 1
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-50",
          )}
          aria-label="Previous page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {Array.from({ length: pageCount }, (_, i) => i + 1).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={cn(
              "w-8 h-8 rounded-btn text-sm font-medium transition-colors",
              p === page
                ? "bg-blue-50 text-primary"
                : "text-slate-500 hover:bg-slate-50",
            )}
          >
            {p}
          </button>
        ))}

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page === pageCount}
          className={cn(
            "p-1.5 rounded-btn transition-colors",
            page === pageCount
              ? "text-slate-300 cursor-not-allowed"
              : "text-slate-500 hover:bg-slate-50",
          )}
          aria-label="Next page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
