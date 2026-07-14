// src/features/ingestion/components/FileDropZone.jsx
//
// Reusable drag-and-drop / click-to-browse file picker. File handling is
// entirely frontend-only: the File object is kept in memory only long
// enough to read its name/size for display and validation.

import { UploadCloud, FileArchive, CheckCircle2, X, AlertCircle } from "lucide-react";
import { cn } from "../../../utils/classNames.js";
import { formatBytes } from "../../../utils/formatBytes.js";

export default function FileDropZone({
  file,
  error,
  isDragging,
  onFileInputChange,
  onDragOver,
  onDragLeave,
  onDrop,
  onRemove,
  accept = ".zip",
  helperText,
}) {
  return (
    <div>
      {file ? (
        <div
          className={cn(
            "flex items-center justify-between gap-3 px-4 py-3.5 rounded-btn border bg-slate-50",
            error ? "border-red-300" : "border-slate-200",
          )}
        >
          <div className="flex items-center gap-3 min-w-0">
            <FileArchive className="w-8 h-8 text-primary shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-700 truncate">
                {file.name}
              </p>
              <p className="text-xs text-slate-400">{formatBytes(file.size)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {error ? (
              <AlertCircle className="w-4 h-4 text-red-500" aria-label="Invalid file" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-green-500" aria-label="Valid file" />
            )}
            <button
              type="button"
              onClick={onRemove}
              className="p-1.5 rounded-btn hover:bg-slate-200 transition-colors"
              aria-label="Remove selected file"
            >
              <X className="w-4 h-4 text-slate-500" />
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center gap-2 px-4 py-8 rounded-btn border-2 border-dashed text-center transition-colors",
            isDragging
              ? "border-primary bg-bgBlueTint"
              : error
                ? "border-red-300 bg-red-50/40"
                : "border-slate-300 bg-slate-50/60 hover:border-primary/40",
          )}
        >
          <UploadCloud className="w-8 h-8 text-slate-400" />
          <p className="text-sm text-slate-500">
            Drag and drop your file here
          </p>
          <p className="text-xs text-slate-400">or</p>
          <label className="inline-flex items-center px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors cursor-pointer">
            Choose File
            <input
              type="file"
              accept={accept}
              onChange={onFileInputChange}
              className="hidden"
              aria-label="Choose file to upload"
            />
          </label>
        </div>
      )}

      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
      {helperText && !error && (
        <p className="text-xs text-slate-400 mt-1.5">{helperText}</p>
      )}
    </div>
  );
}
