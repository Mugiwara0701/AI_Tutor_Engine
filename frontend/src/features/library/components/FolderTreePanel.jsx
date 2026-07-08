// src/features/library/components/FolderTreePanel.jsx
// Placeholder for FolderTreePanel — implement component/logic here.

// src/features/library/components/FolderTreePanel.jsx

import TreeNode from "./TreeNode.jsx";
import StorageUsageBar from "../../../components/shared/StorageUsageBar.jsx";

export default function FolderTreePanel({
  tree,
  isExpanded,
  toggleNode,
  activeId,
  onSelectChapter,
  storage,
}) {
  return (
    <aside className="w-72 shrink-0 bg-white border border-slate-100 rounded-card flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-900">Content Tree</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        <TreeNode
          node={tree}
          isExpanded={isExpanded}
          toggleNode={toggleNode}
          activeId={activeId}
          onSelectChapter={onSelectChapter}
        />
      </div>

      <div className="p-3 border-t border-slate-100">
        <StorageUsageBar usedGB={storage.usedGB} totalGB={storage.totalGB} />
      </div>
    </aside>
  );
}
