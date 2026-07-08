// src/features/library/hooks/useLibraryData.js
// Placeholder for useLibraryData — implement component/logic here.

// src/features/library/hooks/useLibraryData.js

import { useCallback, useMemo, useState } from "react";
import mockLibrary from "../data/mockLibrary.json";

const STATUS_MATCH = {
  Complete: "Complete",
  "In Progress": "In Progress",
  "Not Started": "Not Started",
};

export function useLibraryData() {
  const [selectedChapterId, setSelectedChapterId] = useState(
    mockLibrary.activeChapterId,
  );
  const [expandedNodes, setExpandedNodes] = useState(
    new Set(["root", "class-12", "physics", "physics-part-1"]),
  );
  const [filters, setFilters] = useState({
    class: "",
    subject: "",
    book: "",
    status: "",
    updated: "",
  });

  const toggleNode = useCallback((nodeId) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      next.has(nodeId) ? next.delete(nodeId) : next.add(nodeId);
      return next;
    });
  }, []);

  const isExpanded = useCallback(
    (nodeId) => expandedNodes.has(nodeId),
    [expandedNodes],
  );

  const updateFilter = useCallback((key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({ class: "", subject: "", book: "", status: "", updated: "" });
  }, []);

  const filteredChapters = useMemo(() => {
    return mockLibrary.chapters.filter((chapter) => {
      if (filters.class && !chapter.breadcrumb.includes(filters.class))
        return false;
      if (filters.subject && !chapter.breadcrumb.includes(filters.subject))
        return false;
      if (filters.book && !chapter.breadcrumb.includes(filters.book))
        return false;
      if (filters.status && chapter.status !== STATUS_MATCH[filters.status])
        return false;
      return true;
    });
  }, [filters]);

  const selectedChapter = useMemo(
    () => mockLibrary.chapters.find((c) => c.id === selectedChapterId) ?? null,
    [selectedChapterId],
  );

  return {
    tree: mockLibrary.tree,
    stats: mockLibrary.stats,
    storage: mockLibrary.storage,
    filterOptions: mockLibrary.filterOptions,
    chapters: filteredChapters,
    selectedChapter,
    selectedChapterId,
    setSelectedChapterId,
    isExpanded,
    toggleNode,
    filters,
    updateFilter,
    clearFilters,
  };
}
