// src/components/ui/DataTable/DataTable.jsx
// Placeholder for DataTable — implement component/logic here.

// src/components/ui/DataTable/DataTable.jsx

import { useMemo, useState } from "react";
import TableHeader from "./TableHeader.jsx";
import TablePagination from "./TablePagination.jsx";
import { useTableSort } from "./useTableSort.js";
import EmptyState from "../EmptyState.jsx";
import { cn } from "../../../utils/classNames.js";

/**
 * Generic sortable, selectable, paginated table.
 *
 * @param {Array} columns - [{ key, label, sortable?, align?, width?, render?: (row) => node }]
 * @param {Array} data
 * @param {(row) => string|number} getRowId
 * @param {boolean} selectable
 * @param {Array} selectedIds
 * @param {(ids: Array) => void} onSelectionChange
 * @param {(row) => void} onRowClick
 * @param {number} pageSize
 * @param {string|node} emptyMessage
 */
export default function DataTable({
  columns,
  data = [],
  getRowId = (row) => row.id,
  selectable = false,
  selectedIds = [],
  onSelectionChange,
  onRowClick,
  pageSize = 10,
  emptyTitle = "No results found",
  emptyDescription = "Try adjusting your filters or search terms.",
}) {
  const [page, setPage] = useState(1);
  const { sortedData, sort, toggleSort } = useTableSort(data);

  const pageCount = Math.max(1, Math.ceil(sortedData.length / pageSize));
  const currentPage = Math.min(page, pageCount);

  const pageData = useMemo(() => {
    const startIdx = (currentPage - 1) * pageSize;
    return sortedData.slice(startIdx, startIdx + pageSize);
  }, [sortedData, currentPage, pageSize]);

  const pageIds = pageData.map(getRowId);
  const allSelected =
    pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));

  const handleToggleAll = (checked) => {
    if (!onSelectionChange) return;
    if (checked) {
      onSelectionChange([...new Set([...selectedIds, ...pageIds])]);
    } else {
      onSelectionChange(selectedIds.filter((id) => !pageIds.includes(id)));
    }
  };

  const handleToggleRow = (id) => {
    if (!onSelectionChange) return;
    onSelectionChange(
      selectedIds.includes(id)
        ? selectedIds.filter((sid) => sid !== id)
        : [...selectedIds, id],
    );
  };

  if (data.length === 0) {
    return (
      <div className="bg-white border border-slate-100 rounded-card">
        <EmptyState title={emptyTitle} description={emptyDescription} />
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <TableHeader
            columns={columns}
            sort={sort}
            onSort={toggleSort}
            selectable={selectable}
            allSelected={allSelected}
            onToggleAll={handleToggleAll}
          />
          <tbody>
            {pageData.map((row) => {
              const id = getRowId(row);
              return (
                <tr
                  key={id}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    "border-b border-slate-50 last:border-0 transition-colors",
                    onRowClick && "cursor-pointer hover:bg-slate-50/70",
                  )}
                >
                  {selectable && (
                    <td
                      className="px-4 py-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(id)}
                        onChange={() => handleToggleRow(id)}
                        className="w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary/30"
                      />
                    </td>
                  )}
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-4 py-3 text-sm text-slate-700",
                        col.align === "right" && "text-right",
                      )}
                    >
                      {col.render ? col.render(row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <TablePagination
        page={currentPage}
        pageCount={pageCount}
        totalItems={sortedData.length}
        pageSize={pageSize}
        onPageChange={setPage}
      />
    </div>
  );
}
