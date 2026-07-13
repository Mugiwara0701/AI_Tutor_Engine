// src/features/ingestion/pages/IngestionPage.jsx
//
// Frontend-only Ingestion page. All records, filters, selections and the
// upload simulation live in local React state (see hooks/) — there is no
// backend, API, database, or storage-provider integration here.

import { useState } from "react";
import { useIngestionData } from "../hooks/useIngestionData.js";
import IngestionHeader from "../components/IngestionHeader.jsx";
import IngestionSummaryCards from "../components/IngestionSummaryCards.jsx";
import IngestionFilterBar from "../components/IngestionFilterBar.jsx";
import UploadHistoryTable from "../components/UploadHistoryTable.jsx";
import SelectedUploadPanel from "../components/SelectedUploadPanel.jsx";
import IngestionPipelineProgress from "../components/IngestionPipelineProgress.jsx";
import UploadNewBookModal from "../components/UploadNewBookModal.jsx";
import ViewUploadDetailsModal from "../components/ViewUploadDetailsModal.jsx";
import InlineAlert from "../../../components/shared/InlineAlert.jsx";

export default function IngestionPage() {
  const {
    uploads,
    summary,
    filterOptions,
    filters,
    updateFilter,
    selectedUpload,
    setSelectedId,
    selectedIds,
    setSelectedIds,
    addUpload,
  } = useIngestionData();

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const handleUploaded = (entry) => {
    addUpload({
      book: entry.book,
      board: entry.board,
      class: entry.class,
      subject: entry.subject,
      curriculum: entry.curriculumYear,
      version: "v1",
      fileName: entry.file.name,
      fileSize: entry.file.size,
      storagePath: `../BOOK_ZIP/${entry.board}/${entry.class.replace(
        " ",
        "_",
      )}/${entry.subject}/${entry.book.replace(/\s+/g, "_")}_v1/${entry.file.name}`,
    });
    setIsUploadModalOpen(false);
    setToast({ type: "success", message: `${entry.book} was added to the ingestion queue.` });
  };

  return (
    <div className="flex flex-col gap-5">
      {toast && (
        <div className="fixed top-20 right-6 z-[60] w-80">
          <InlineAlert
            type={toast.type}
            message={toast.message}
            onDismiss={() => setToast(null)}
          />
        </div>
      )}

      <IngestionHeader onUploadClick={() => setIsUploadModalOpen(true)} />

      <IngestionSummaryCards summary={summary} />

      <IngestionFilterBar
        filters={filters}
        filterOptions={filterOptions}
        onChange={updateFilter}
        onApply={() => {}}
      />

      <div className="flex flex-col xl:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0">
          <UploadHistoryTable
            uploads={uploads}
            onSelectUpload={setSelectedId}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
          />
        </div>

        <div className="w-full xl:w-96 shrink-0 flex flex-col gap-5">
          <SelectedUploadPanel
            upload={selectedUpload}
            onViewDetails={() => setIsDetailsModalOpen(true)}
          />
          <IngestionPipelineProgress upload={selectedUpload} />
        </div>
      </div>

      <UploadNewBookModal
        open={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUploaded={handleUploaded}
      />

      <ViewUploadDetailsModal
        open={isDetailsModalOpen}
        onClose={() => setIsDetailsModalOpen(false)}
        upload={selectedUpload}
      />
    </div>
  );
}
