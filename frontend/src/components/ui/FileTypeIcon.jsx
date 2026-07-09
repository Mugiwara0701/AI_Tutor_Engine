// src/components/ui/FileTypeIcon.jsx
// Placeholder for FileTypeIcon — implement component/logic here.

// src/components/ui/FileTypeIcon.jsx

import {
  FileText,
  Presentation,
  FileSpreadsheet,
  FileVideo,
  FileArchive,
  FileImage,
  File,
} from "lucide-react";
import { cn } from "../../utils/classNames.js";

const TYPE_CONFIG = {
  pdf: { icon: FileText, className: "bg-red-50 text-red-500" },
  pptx: { icon: Presentation, className: "bg-orange-50 text-orange-500" },
  ppt: { icon: Presentation, className: "bg-orange-50 text-orange-500" },
  xlsx: { icon: FileSpreadsheet, className: "bg-green-50 text-green-500" },
  xls: { icon: FileSpreadsheet, className: "bg-green-50 text-green-500" },
  docx: { icon: FileText, className: "bg-blue-50 text-blue-500" },
  doc: { icon: FileText, className: "bg-blue-50 text-blue-500" },
  mp4: { icon: FileVideo, className: "bg-purple-50 text-purple-500" },
  zip: { icon: FileArchive, className: "bg-yellow-50 text-yellow-600" },
  png: { icon: FileImage, className: "bg-teal-50 text-teal-500" },
  jpg: { icon: FileImage, className: "bg-teal-50 text-teal-500" },
  jpeg: { icon: FileImage, className: "bg-teal-50 text-teal-500" },
};

const DEFAULT_CONFIG = { icon: File, className: "bg-slate-100 text-slate-400" };

/**
 * Icon badge for a file type. Pass either `type` ("pdf", "zip", ...) directly,
 * or `fileName` and the extension will be inferred.
 */
export default function FileTypeIcon({
  type,
  fileName,
  size = "md",
  className,
}) {
  const ext = (type ?? fileName?.split(".").pop() ?? "").toLowerCase();
  const config = TYPE_CONFIG[ext] ?? DEFAULT_CONFIG;
  const Icon = config.icon;

  const boxSize =
    size === "sm" ? "w-7 h-7" : size === "lg" ? "w-11 h-11" : "w-9 h-9";
  const iconSize =
    size === "sm" ? "w-3.5 h-3.5" : size === "lg" ? "w-5 h-5" : "w-4 h-4";

  return (
    <div
      className={cn(
        "rounded-btn flex items-center justify-center shrink-0",
        boxSize,
        config.className,
        className,
      )}
    >
      <Icon className={iconSize} />
    </div>
  );
}
