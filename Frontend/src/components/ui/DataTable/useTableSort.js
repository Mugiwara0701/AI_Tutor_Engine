// src/components/ui/DataTable/useTableSort.js
// Placeholder for useTableSort — implement component/logic here.

// src/components/ui/DataTable/useTableSort.js

import { useMemo, useState } from "react";

/**
 * Generic client-side sort hook for DataTable.
 * @param {Array} data
 * @param {{ key: string, direction: 'asc'|'desc' } | null} initialSort
 */
export function useTableSort(data, initialSort = null) {
  const [sort, setSort] = useState(initialSort);

  const sortedData = useMemo(() => {
    if (!sort?.key) return data;

    const sorted = [...data].sort((a, b) => {
      const aVal = a[sort.key];
      const bVal = b[sort.key];

      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      if (typeof aVal === "number" && typeof bVal === "number") {
        return aVal - bVal;
      }
      return String(aVal).localeCompare(String(bVal));
    });

    return sort.direction === "desc" ? sorted.reverse() : sorted;
  }, [data, sort]);

  const toggleSort = (key) => {
    setSort((prev) => {
      if (prev?.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  };

  return { sortedData, sort, toggleSort };
}
