// src/features/zip-manager/pages/ZipManagerPage.jsx

import { Upload, Plus } from "lucide-react";
import { useZipData } from "../hooks/useZipData.js";
import ZipFilterBar from "../components/ZipFilterBar.jsx";
import ZipFilesTable from "../components/ZipFilesTable.jsx";
import ZipDetailsPanel from "../components/ZipDetailsPanel.jsx";
import StorageUsageBar from "../../../components/shared/StorageUsageBar.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import TopicZipUploadSection from "../components/TopicZipUploadSection.jsx";

export default function ZipManagerPage() {
  const {
    zips,
    filterOptions,
    storage,
    filters,
    updateFilter,
    clearFilters,
    selectedZip,
    setSelectedZipId,
    selectedIds,
    setSelectedIds,
  } = useZipData();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">ZIP Manager</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Upload, browse, and manage generated content packages.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Upload ZIP
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New ZIP
          </button>
          <ActionMenu
            items={[
              { label: "Export list as CSV", onClick: () => {} },
              { label: "Refresh", onClick: () => {} },
            ]}
          />
        </div>
      </div>

      <ZipFilterBar
        filters={filters}
        filterOptions={filterOptions}
        onChange={updateFilter}
        onClear={clearFilters}
      />

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0 flex flex-col gap-5">
          <ZipFilesTable
            zips={zips}
            onSelectZip={setSelectedZipId}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
          />
          <StorageUsageBar usedGB={storage.usedGB} totalGB={storage.totalGB} />

          <TopicZipUploadSection />
        </div>

        <ZipDetailsPanel zip={selectedZip} />
      </div>
    </div>
  );
}
