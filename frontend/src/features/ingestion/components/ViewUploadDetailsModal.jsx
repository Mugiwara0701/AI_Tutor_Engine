// src/features/ingestion/components/ViewUploadDetailsModal.jsx
//
// Frontend-only placeholder detail view opened from the Selected Upload
// panel's "View Details" action. No API calls are made here.

import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import IngestionStatusBadge from "./IngestionStatusBadge.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import { formatBytes } from "../../../utils/formatBytes.js";

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-700 text-right">
        {value}
      </span>
    </div>
  );
}

export default function ViewUploadDetailsModal({ open, onClose, upload }) {
  if (!upload) return null;

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Upload Details"
      maxWidth="lg"
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-start gap-3">
          <FileTypeIcon type="zip" size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold text-slate-800 truncate">
                {upload.book}
              </p>
              <IngestionStatusBadge status={upload.status} />
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {upload.board} &middot; {upload.class} &middot; {upload.subject}
            </p>
          </div>
        </div>

        <div>
          <ProgressBar
            value={upload.progress}
            label={upload.currentStage}
            color={
              upload.status === "Completed"
                ? "green"
                : upload.status === "Failed"
                  ? "red"
                  : "primary"
            }
          />
        </div>

        <div>
          <Row label="Curriculum Year" value={upload.curriculum} />
          <Row label="Version" value={upload.version} />
          <Row
            label="Uploaded By"
            value={
              <span className="inline-flex items-center gap-1.5">
                <UserAvatar name={upload.uploadedBy?.name} size="sm" />
                {upload.uploadedBy?.name}
              </span>
            }
          />
          <Row label="Uploaded On" value={upload.uploadedOnDisplay} />
          <Row label="File Name" value={upload.fileName} />
          <Row label="File Size" value={formatBytes(upload.fileSize)} />
          <Row label="Storage Path" value={upload.storagePath} />
        </div>

        <div className="flex justify-end pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </ModalDialog>
  );
}
