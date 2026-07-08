// src/features/library/pages/LibraryPage.jsx
// Placeholder for LibraryPage — implement component/logic here.

// src/features/library/pages/LibraryPage.jsx

import { useLibraryData } from "../hooks/useLibraryData.js";
import FolderTreePanel from "../components/FolderTreePanel.jsx";
import LibraryStatsRow from "../components/LibraryStatsRow.jsx";
import LibraryFilterBar from "../components/LibraryFilterBar.jsx";
import ChapterTable from "../components/ChapterTable.jsx";
import ChapterPreviewCard from "../components/ChapterPreviewCard.jsx";

export default function LibraryPage() {
  const {
    tree,
    stats,
    storage,
    filterOptions,
    chapters,
    selectedChapter,
    selectedChapterId,
    setSelectedChapterId,
    isExpanded,
    toggleNode,
    filters,
    updateFilter,
    clearFilters,
  } = useLibraryData();

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      <FolderTreePanel
        tree={tree}
        isExpanded={isExpanded}
        toggleNode={toggleNode}
        activeId={selectedChapterId}
        onSelectChapter={setSelectedChapterId}
        storage={storage}
      />

      <div className="flex-1 min-w-0 flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Library</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Browse and manage all classes, subjects, books, chapters, and
            topics.
          </p>
        </div>

        <LibraryStatsRow stats={stats} />

        <LibraryFilterBar
          filterOptions={filterOptions}
          filters={filters}
          onChange={updateFilter}
          onClear={clearFilters}
        />

        <ChapterTable
          chapters={chapters}
          selectedChapterId={selectedChapterId}
          onSelectChapter={setSelectedChapterId}
        />

        <ChapterPreviewCard chapter={selectedChapter} />
      </div>
    </div>
  );
}
