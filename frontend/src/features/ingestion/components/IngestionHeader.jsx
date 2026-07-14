// src/features/ingestion/components/IngestionHeader.jsx

import { Plus } from "lucide-react";

export default function IngestionHeader({ onUploadClick }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Ingestion</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Upload new NCERT books and monitor ingestion into the AI Tutor
          pipeline.
        </p>
      </div>

      <button
        type="button"
        onClick={onUploadClick}
        className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
      >
        <Plus className="w-4 h-4" />
        Upload New Book
      </button>
    </div>
  );
}
