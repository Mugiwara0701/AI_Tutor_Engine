// src/features/global-search/pages/GlobalSearchPage.jsx
// Placeholder for GlobalSearchPage — implement component/logic here.

// src/features/global-search/pages/GlobalSearchPage.jsx

import { BookOpen, FileText, Folder, Code2 } from "lucide-react";
import { useSearch } from "../hooks/useSearch.js";
import SearchHeader from "../components/SearchHeader.jsx";
import SearchTabsFilter from "../components/SearchTabsFilter.jsx";
import ResultsSection, {
  EmptyResultsState,
} from "../components/ResultsSection.jsx";
import SearchFiltersPanel from "../components/SearchFiltersPanel.jsx";
import RecentSearchesList from "../components/RecentSearchesList.jsx";
import QuickActionsCard from "../components/QuickActionsCard.jsx";

const SECTION_CONFIG = [
  {
    key: "chapters",
    title: "Chapters",
    icon: BookOpen,
    iconClassName: "bg-blue-50 text-primary",
  },
  {
    key: "topics",
    title: "Topics",
    icon: FileText,
    iconClassName: "bg-slate-100 text-slate-500",
  },
  {
    key: "resources",
    title: "Resources",
    icon: Folder,
    iconClassName: "bg-yellow-50 text-yellow-600",
  },
  {
    key: "prompts",
    title: "Prompts",
    icon: Code2,
    iconClassName: "bg-purple-50 text-purple-600",
  },
  {
    key: "files",
    title: "Files",
    icon: Folder,
    iconClassName: "bg-blue-50 text-primary",
  },
];

export default function GlobalSearchPage() {
  const {
    query,
    setQuery,
    activeTab,
    setActiveTab,
    filters,
    updateFilter,
    applyFilters,
    filterOptions,
    recentSearches,
    removeRecentSearch,
    selectRecentSearch,
    filteredResults,
    counts,
  } = useSearch();

  const visibleSections = SECTION_CONFIG.filter(
    (section) => activeTab === "all" || activeTab === section.key,
  );
  const hasAnyResults = visibleSections.some(
    (section) => filteredResults[section.key].length > 0,
  );

  return (
    <div className="flex flex-col gap-5">
      <SearchHeader query={query} onChange={setQuery} />

      <SearchTabsFilter
        activeTab={activeTab}
        onChange={setActiveTab}
        counts={counts}
      />

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          {hasAnyResults ? (
            visibleSections.map((section) => (
              <ResultsSection
                key={section.key}
                title={section.title}
                icon={section.icon}
                iconClassName={section.iconClassName}
                results={filteredResults[section.key]}
              />
            ))
          ) : (
            <EmptyResultsState />
          )}
        </div>

        <div className="w-full lg:w-80 shrink-0 flex flex-col gap-5">
          <SearchFiltersPanel
            filters={filters}
            filterOptions={filterOptions}
            onChange={updateFilter}
            onApply={applyFilters}
          />
          <RecentSearchesList
            searches={recentSearches}
            onSelect={selectRecentSearch}
            onRemove={removeRecentSearch}
          />
          <QuickActionsCard />
        </div>
      </div>
    </div>
  );
}
