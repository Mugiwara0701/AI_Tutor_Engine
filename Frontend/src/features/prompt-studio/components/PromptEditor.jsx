// src/features/prompt-studio/components/PromptEditor.jsx
// Placeholder for PromptEditor — implement component/logic here.

// src/features/prompt-studio/components/PromptEditor.jsx

import { Clock } from "lucide-react";
import SyntaxHighlighter from "./SyntaxHighlighter.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import { formatDate } from "../../../utils/formatDate.js";

export default function PromptEditor({
  content,
  stats,
  updatedOn,
  updatedBy,
  revertedNotice,
}) {
  const lines = content.split("\n");

  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      {revertedNotice && (
        <div className="px-4 py-2 bg-blue-50 border-b border-blue-100 text-xs text-blue-700 flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          {revertedNotice}
        </div>
      )}

      <div className="bg-[#1E1E2E] font-mono text-sm overflow-x-auto">
        <div className="flex min-w-full w-max">
          <div className="select-none px-3 py-4 text-right text-slate-500 border-r border-white/5">
            {lines.map((_, i) => (
              <div key={i} className="leading-6 pr-1">
                {i + 1}
              </div>
            ))}
          </div>
          <div className="px-4 py-4 flex-1">
            {lines.map((line, i) => (
              <div key={i} className="leading-6 whitespace-pre">
                <SyntaxHighlighter line={line} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-slate-100 text-xs text-slate-500">
        <div className="flex flex-wrap items-center gap-4">
          <span>
            <span className="font-medium text-slate-700">
              {stats.tokens.toLocaleString()}
            </span>{" "}
            Tokens
          </span>
          <span>
            <span className="font-medium text-slate-700">
              {stats.characters.toLocaleString()}
            </span>{" "}
            Characters
          </span>
          <span>
            <span className="font-medium text-slate-700">
              {stats.words.toLocaleString()}
            </span>{" "}
            Words
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span>
            Last Updated:{" "}
            <span className="font-medium text-slate-700">
              {formatDate(updatedOn)}
            </span>
          </span>
          {updatedBy && <UserAvatar name={updatedBy.name} size="sm" />}
        </div>
      </div>
    </div>
  );
}
