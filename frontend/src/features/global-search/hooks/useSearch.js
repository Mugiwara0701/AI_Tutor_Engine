// src/features/global-search/hooks/useSearch.js
// Placeholder for useSearch — implement component/logic here.

// src/features/global-search/hooks/useSearch.js

import { useMemo, useState } from "react";
import mockSearchResults from "../data/mockSearchResults.json";

const INITIAL_FILTERS = {
  class: "",
  subject: "",
  book: "",
  contentType: "",
  status: "",
  dateFrom: "",
  dateTo: "",
};

export function useSearch() {
  const [query, setQuery] = useState("coulomb");
  const [activeTab, setActiveTab] = useState("all");
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [recentSearches, setRecentSearches] = useState(
    mockSearchResults.recentSearches,
  );

  const updateFilter = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const applyFilters = () => {
    // In a real app this would trigger a refetch; mock data is filtered
    // client-side already via `filteredResults` below.
  };

  const removeRecentSearch = (id) =>
    setRecentSearches((prev) => prev.filter((s) => s.id !== id));

  const selectRecentSearch = (searchQuery) => setQuery(searchQuery);

  const filteredResults = useMemo(() => {
    const q = query.trim().toLowerCase();

    const matches = (item) => {
      if (q && !item.name.toLowerCase().includes(q)) return false;
      if (filters.status && item.status !== filters.status) return false;
      if (
        filters.class &&
        !item.breadcrumb.toLowerCase().includes(filters.class.toLowerCase())
      )
        return false;
      if (
        filters.subject &&
        !item.breadcrumb.toLowerCase().includes(filters.subject.toLowerCase())
      )
        return false;
      if (
        filters.book &&
        !item.breadcrumb.toLowerCase().includes(filters.book.toLowerCase())
      )
        return false;
      return true;
    };

    const sections = mockSearchResults.results;
    return {
      chapters: sections.chapters.filter(matches),
      topics: sections.topics.filter(matches),
      resources: sections.resources.filter(matches),
      prompts: sections.prompts.filter(matches),
      files: sections.files.filter(matches),
    };
  }, [query, filters]);

  const counts = useMemo(() => {
    const total = Object.values(filteredResults).reduce(
      (sum, list) => sum + list.length,
      0,
    );
    return {
      all: total,
      chapters: filteredResults.chapters.length,
      topics: filteredResults.topics.length,
      resources: filteredResults.resources.length,
      prompts: filteredResults.prompts.length,
      files: filteredResults.files.length,
    };
  }, [filteredResults]);

  return {
    query,
    setQuery,
    activeTab,
    setActiveTab,
    filters,
    updateFilter,
    applyFilters,
    filterOptions: mockSearchResults.filterOptions,
    recentSearches,
    removeRecentSearch,
    selectRecentSearch,
    filteredResults,
    counts,
  };
}
