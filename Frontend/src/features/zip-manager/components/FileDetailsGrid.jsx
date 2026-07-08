// src/features/zip-manager/components/FileDetailsGrid.jsx
// Placeholder for FileDetailsGrid — implement component/logic here.

// src/features/zip-manager/components/FileDetailsGrid.jsx

import { formatBytes } from "../../../utils/formatBytes.js";
import { cn } from "../../../utils/classNames.js";

export default function FileDetailsGrid({ zip }) {
  const details = [
    { label: "Size", value: formatBytes(zip.sizeBytes) },
    { label: "Files", value: zip.filesCount },
    { label: "Folders", value: zip.foldersCount },
    { label: "Type", value: "ZIP Archive" },
    { label: "Compression", value: zip.compression },
    { label: "Checksum", value: zip.checksum, mono: true },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {details.map((d) => (
        <div key={d.label} className="bg-bgLight rounded-btn px-3 py-2">
          <p className="text-xs text-slate-400">{d.label}</p>
          <p
            className={cn(
              "text-sm font-medium text-slate-700 truncate",
              d.mono && "font-mono",
            )}
          >
            {d.value}
          </p>
        </div>
      ))}
    </div>
  );
}
