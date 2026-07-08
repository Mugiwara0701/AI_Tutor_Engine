// src/features/global-search/components/ResultRow.jsx
// Placeholder for ResultRow — implement component/logic here.

// src/features/global-search/components/ResultRow.jsx

import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import { formatDate } from "../../../utils/formatDate.js";

export default function ResultRow({ icon: Icon, iconClassName, result }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50/70 transition-colors">
      <div
        className={`w-8 h-8 rounded-btn flex items-center justify-center shrink-0 ${iconClassName}`}
      >
        <Icon className="w-4 h-4" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-800 truncate">
          {result.name}
        </p>
        <p className="text-xs text-slate-400 truncate">{result.breadcrumb}</p>
      </div>

      {result.status && <StatusBadge status={result.status} />}

      <span className="text-xs text-slate-400 w-20 text-right shrink-0">
        {formatDate(result.date)}
      </span>

      <ActionMenu
        items={[
          { label: "Open", onClick: () => {} },
          { label: "Copy link", onClick: () => {} },
        ]}
      />
    </div>
  );
}
