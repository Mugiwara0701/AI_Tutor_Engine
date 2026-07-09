// src/features/storage-explorer/pages/StorageExplorerPage.jsx
// Placeholder for StorageExplorerPage — implement component/logic here.

// src/features/storage-explorer/pages/StorageExplorerPage.jsx

import { FolderPlus, RefreshCw, Upload, UploadCloud } from "lucide-react";
import { useStorageData } from "../hooks/useStorageData.js";
import FolderTree from "../components/FolderTree.jsx";
import StorageCircularProgress from "../components/StorageCircularProgress.jsx";
import ViewToggle from "../components/ViewToggle.jsx";
import FileBrowserTable from "../components/FileBrowserTable.jsx";
import StorageStatsBar from "../components/StorageStatsBar.jsx";
import BreadcrumbNav from "../../../layouts/Navbar/BreadcrumbNav.jsx";

export default function StorageExplorerPage() {
  const {
    tree,
    storage,
    isExpanded,
    toggleNode,
    activeFolderId,
    setActiveFolderId,
    breadcrumb,
    files,
    stats,
    viewMode,
    setViewMode,
    pageSize,
    setPageSize,
    selectedIds,
    setSelectedIds,
  } = useStorageData();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Storage Explorer
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Browse and manage every generated file across your content tree.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <FolderPlus className="w-4 h-4" />
            New Folder
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Upload Files
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <UploadCloud className="w-4 h-4" />
            Upload Folder
          </button>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <aside className="w-full lg:w-72 shrink-0 bg-white border border-slate-100 rounded-card flex flex-col">
          <div className="px-4 py-3 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">
              Folder Tree
            </h2>
          </div>

          <FolderTree
            tree={tree}
            isExpanded={isExpanded}
            toggleNode={toggleNode}
            activeId={activeFolderId}
            onSelect={setActiveFolderId}
          />

          <div className="border-t border-slate-100">
            <StorageCircularProgress
              usedGB={storage.usedGB}
              totalGB={storage.totalGB}
            />
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <BreadcrumbNav items={breadcrumb} />
            <ViewToggle value={viewMode} onChange={setViewMode} />
          </div>

          <FileBrowserTable
            files={files}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
          />
        </div>
      </div>

      <StorageStatsBar stats={stats} />
    </div>
  );
}
