// src/features/zip-manager/components/ZipDetailsPanel.jsx

import { Eye, Download } from "lucide-react";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import FileTypeIcon from "../../../components/ui/FileTypeIcon.jsx";
import FileDetailsGrid from "./FileDetailsGrid.jsx";
import ContentsPreviewList from "./ContentsPreviewList.jsx";
import ZipActivityLog from "./ZipActivityLog.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";
import { formatDate } from "../../../utils/formatDate.js";

export default function ZipDetailsPanel({ zip }) {
  if (!zip) {
    return (
      <div className="bg-white border border-slate-100 rounded-card w-full lg:w-80 shrink-0 lg:sticky lg:top-5">
        <EmptyState
          title="No ZIP selected"
          description="Select a ZIP package from the table to see its details."
        />
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-100 rounded-card w-full lg:w-80 shrink-0 lg:sticky lg:top-5 lg:max-h-[calc(100vh-2.5rem)] lg:overflow-y-auto flex flex-col gap-5 p-5">
      <div className="flex items-start gap-3">
        <FileTypeIcon type="zip" size="lg" />
        <div className="min-w-0">
          <p className="font-semibold text-slate-800 truncate">{zip.name}</p>
          <div className="mt-1">
            <StatusBadge status={zip.status} />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 text-xs text-slate-500">
        <div className="flex justify-between">
          <span>Created on</span>
          <span className="font-medium text-slate-700">
            {formatDate(zip.createdOn)}
          </span>
        </div>
        <div className="flex justify-between">
          <span>Updated on</span>
          <span className="font-medium text-slate-700">
            {formatDate(zip.updatedOn)}
          </span>
        </div>
        <div className="flex justify-between items-center">
          <span>Updated by</span>
          <UserAvatar name={zip.updatedBy?.name} size="sm" />
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          className="flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <Eye className="w-4 h-4" />
          Preview
        </button>
        <button
          type="button"
          className="flex-1 flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Download className="w-4 h-4" />
          Download
        </button>
      </div>

      <div>
        <p className="text-sm font-semibold text-slate-800 mb-2.5">
          File Details
        </p>
        <FileDetailsGrid zip={zip} />
      </div>

      <ContentsPreviewList contents={zip.contents} />

      <ZipActivityLog activity={zip.activity} />
    </div>
  );
}
