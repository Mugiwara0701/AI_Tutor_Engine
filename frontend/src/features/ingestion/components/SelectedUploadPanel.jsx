// src/features/ingestion/components/SelectedUploadPanel.jsx

import { ExternalLink } from "lucide-react";
import IngestionStatusBadge from "./IngestionStatusBadge.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";
import { formatBytes } from "../../../utils/formatBytes.js";

function DetailRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs font-medium text-slate-700 text-right truncate max-w-[62%]">
        {children}
      </span>
    </div>
  );
}

export default function SelectedUploadPanel({ upload, onViewDetails }) {
  if (!upload) {
    return (
      <div className="bg-white border border-slate-100 rounded-card">
        <EmptyState
          title="No upload selected"
          description="Select a row from the Upload History table to see its details here."
        />
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-100 rounded-card p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">
          Selected Upload
        </h2>
        <button
          type="button"
          onClick={() => onViewDetails(upload)}
          className="flex items-center gap-1 text-xs font-medium text-primary hover:text-blue-700 transition-colors"
        >
          View Details
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>

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
            {upload.board} &middot; {upload.class} &middot; {upload.subject}{" "}
            &middot; {upload.curriculum}
          </p>
          <p className="text-xs text-slate-400">Version: {upload.version}</p>
        </div>
      </div>

      <div className="border-t border-slate-100 pt-3">
        <DetailRow label="Uploaded By">
          <span className="inline-flex items-center gap-1.5 justify-end">
            <UserAvatar name={upload.uploadedBy?.name} size="sm" />
            {upload.uploadedBy?.name}
          </span>
        </DetailRow>
        <DetailRow label="Uploaded On">{upload.uploadedOnDisplay}</DetailRow>
        <DetailRow label="File Name">{upload.fileName}</DetailRow>
        <DetailRow label="File Size">{formatBytes(upload.fileSize)}</DetailRow>
        <DetailRow label="Storage Path">{upload.storagePath}</DetailRow>
        <DetailRow label="Current Status">
          <IngestionStatusBadge status={upload.status} />
        </DetailRow>
      </div>
    </div>
  );
}
