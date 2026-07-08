// src/features/zip-manager/hooks/useZipData.js
// Placeholder for useZipData — implement component/logic here.

// src/features/zip-manager/hooks/useZipData.js

import { useMemo, useState } from "react";
import mockZips from "../data/mockZips.json";

const INITIAL_FILTERS = {
  search: "",
  class: "",
  subject: "",
  chapter: "",
  status: "",
};

export function useZipData() {
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [selectedZipId, setSelectedZipId] = useState(
    mockZips.zips[0]?.id ?? null,
  );
  const [selectedIds, setSelectedIds] = useState([]);

  const updateFilter = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: value }));
  const clearFilters = () => setFilters(INITIAL_FILTERS);

  const filteredZips = useMemo(() => {
    return mockZips.zips.filter((zip) => {
      const query = filters.search.toLowerCase();
      if (
        query &&
        !zip.name.toLowerCase().includes(query) &&
        !zip.description.toLowerCase().includes(query)
      )
        return false;
      if (filters.class && zip.class !== filters.class) return false;
      if (filters.subject && zip.subject !== filters.subject) return false;
      if (filters.chapter && zip.chapterTopic !== filters.chapter) return false;
      if (filters.status && zip.status !== filters.status) return false;
      return true;
    });
  }, [filters]);

  const selectedZip = useMemo(
    () => mockZips.zips.find((z) => z.id === selectedZipId) ?? null,
    [selectedZipId],
  );

  return {
    zips: filteredZips,
    filterOptions: mockZips.filterOptions,
    storage: mockZips.storage,
    filters,
    updateFilter,
    clearFilters,
    selectedZip,
    selectedZipId,
    setSelectedZipId,
    selectedIds,
    setSelectedIds,
  };
}
