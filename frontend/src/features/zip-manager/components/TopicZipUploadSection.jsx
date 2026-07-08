// src/features/zip-manager/components/TopicZipUploadSection.jsx
//
// Frontend-only "Topic-wise ZIP Upload" workflow. Nothing here talks to a
// backend or database — everything is held in local React state.

import { useState } from "react";
import { UploadCloud, FolderArchive } from "lucide-react";
import { useTopicZipUploads } from "../hooks/useTopicZipUploads.js";
import TopicZipUploadModal from "./TopicZipUploadModal.jsx";
import TopicZipUploadTable from "./TopicZipUploadTable.jsx";
import InlineAlert from "../../../components/shared/InlineAlert.jsx";

export default function TopicZipUploadSection() {
  const {
    uploads,
    classOptions,
    subjectOptions,
    chapterOptions,
    topicsByChapter,
    addUpload,
    replaceFile,
    deleteUpload,
  } = useTopicZipUploads();

  const [modalOpen, setModalOpen] = useState(false);
  const [alert, setAlert] = useState(null);

  const handleSubmit = (entry) => {
    addUpload(entry);
    setAlert({
      type: "success",
      message: `“${entry.fileName}” was uploaded for ${entry.topicName}.`,
    });
    setModalOpen(false);
  };

  const handleView = (row) => {
    setAlert({
      type: "success",
      message: `Preview isn't wired up yet — this is a frontend placeholder for “${row.fileName}”.`,
    });
  };

  const handleDownload = (row) => {
    setAlert({
      type: "success",
      message: `Download isn't wired up yet — this is a frontend placeholder for “${row.fileName}”.`,
    });
  };

  const handleReplace = (id, fileName) => {
    replaceFile(id, fileName);
    setAlert({ type: "success", message: `File replaced with “${fileName}”.` });
  };

  const handleDelete = (id) => {
    const upload = uploads.find((u) => u.id === id);
    deleteUpload(id);
    setAlert({
      type: "success",
      message: `“${upload?.fileName ?? "File"}” was removed.`,
    });
  };

  return (
    <section className="bg-white border border-slate-100 rounded-card p-5 sm:p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-btn bg-bgBlueTint flex items-center justify-center shrink-0">
            <FolderArchive className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Topic-wise ZIP Upload
            </h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Upload a ZIP package for a specific topic within a chapter.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors shrink-0"
        >
          <UploadCloud className="w-4 h-4" />
          Upload ZIP
        </button>
      </div>

      {alert && (
        <InlineAlert
          type={alert.type}
          message={alert.message}
          onDismiss={() => setAlert(null)}
        />
      )}

      <TopicZipUploadTable
        uploads={uploads}
        onView={handleView}
        onDownload={handleDownload}
        onReplace={handleReplace}
        onDelete={handleDelete}
      />

      <TopicZipUploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSubmit}
        classOptions={classOptions}
        subjectOptions={subjectOptions}
        chapterOptions={chapterOptions}
        topicsByChapter={topicsByChapter}
      />
    </section>
  );
}
