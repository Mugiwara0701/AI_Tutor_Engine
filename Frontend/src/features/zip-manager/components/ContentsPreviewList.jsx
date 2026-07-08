// src/features/zip-manager/components/ContentsPreviewList.jsx
// Placeholder for ContentsPreviewList — implement component/logic here.

// src/features/zip-manager/components/ContentsPreviewList.jsx

import { Folder } from "lucide-react";

export default function ContentsPreviewList({ contents }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2.5">
        <p className="text-sm font-semibold text-slate-800">Contents Preview</p>
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
        >
          View All
        </button>
      </div>
      <ul className="flex flex-col gap-2">
        {contents.map((c) => (
          <li
            key={c.folder}
            className="flex items-center justify-between gap-2 px-3 py-2 rounded-btn bg-bgLight"
          >
            <span className="flex items-center gap-2 text-sm text-slate-700 min-w-0">
              <Folder className="w-4 h-4 text-slate-400 shrink-0" />
              <span className="truncate">{c.folder}</span>
            </span>
            <span className="text-xs text-slate-400 shrink-0">
              {c.filesCount} files
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
