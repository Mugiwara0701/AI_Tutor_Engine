// src/features/ingestion/hooks/useIngestionData.js
//
// Central frontend-only state for the Ingestion page: filters, search,
// the local Upload History list, and the currently selected row. Nothing
// here talks to a backend — everything is derived from the mock data file
// and kept in React state.

import { useMemo, useState } from "react";
import mockIngestion from "../data/mockIngestion.json";

const INITIAL_FILTERS = {
  board: "CBSE",
  class: "Class 12",
  subject: "Physics",
  curriculum: "",
  status: "",
  search: "",
};

let idCounter = mockIngestion.uploads.length + 1;
function generateId() {
  return `ing_${String(idCounter++).padStart(3, "0")}`;
}

export function useIngestionData() {
  const [uploads, setUploads] = useState(mockIngestion.uploads);
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [selectedId, setSelectedId] = useState(mockIngestion.uploads[0]?.id ?? null);
  const [selectedIds, setSelectedIds] = useState([]);

  const updateFilter = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const clearFilters = () => setFilters(INITIAL_FILTERS);

  const filteredUploads = useMemo(() => {
    const query = filters.search.trim().toLowerCase();
    return uploads.filter((row) => {
      if (query && !row.book.toLowerCase().includes(query)) return false;
      if (filters.board && row.board !== filters.board) return false;
      if (filters.class && row.class !== filters.class) return false;
      if (filters.subject && row.subject !== filters.subject) return false;
      if (filters.curriculum && row.curriculum !== filters.curriculum)
        return false;
      if (filters.status && row.status !== filters.status) return false;
      return true;
    });
  }, [uploads, filters]);

  const selectedUpload = useMemo(
    () => uploads.find((row) => row.id === selectedId) ?? null,
    [uploads, selectedId],
  );

  // Adds a freshly "uploaded" book to the top of the Upload History list.
  const addUpload = (entry) => {
    const newUpload = {
      id: generateId(),
      status: "Queued",
      progress: 0,
      currentStage: "File Uploaded",
      uploadedBy: { name: "Mohit Mali" },
      uploadedOn: new Date().toISOString(),
      uploadedOnDisplay: new Date().toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
      pipeline: [
        { id: "s1", name: "File Uploaded", status: "Completed", progress: 100 },
        { id: "s2", name: "Metadata Validated", status: "Pending", progress: 0 },
        { id: "s3", name: "Uploaded to Storage", status: "Pending", progress: 0 },
        { id: "s4", name: "Extraction", status: "Pending", progress: 0 },
        { id: "s5", name: "Phase 1 Processing", status: "Pending", progress: 0 },
        { id: "s6", name: "Phase 2 Processing", status: "Pending", progress: 0 },
        {
          id: "s7",
          name: "Master JSON Generation",
          status: "Pending",
          progress: 0,
        },
      ],
      ...entry,
    };
    setUploads((prev) => [newUpload, ...prev]);
    setSelectedId(newUpload.id);
    return newUpload;
  };

  return {
    uploads: filteredUploads,
    totalCount: uploads.length,
    summary: mockIngestion.summary,
    filterOptions: mockIngestion.filterOptions,
    filters,
    updateFilter,
    clearFilters,
    selectedUpload,
    selectedId,
    setSelectedId,
    selectedIds,
    setSelectedIds,
    addUpload,
  };
}
