// src/features/library/components/TreeNode.jsx
// Placeholder for TreeNode — implement component/logic here.

// src/features/library/components/TreeNode.jsx

import { ChevronRight, Folder, BookOpen, FileText, Layers } from "lucide-react";
import { cn } from "../../../utils/classNames.js";

const ICONS = {
  root: Layers,
  class: Folder,
  subject: Folder,
  book: Folder,
  chapter: BookOpen,
  topic: FileText,
};

export default function TreeNode({
  node,
  level = 0,
  isExpanded,
  toggleNode,
  activeId,
  onSelectChapter,
}) {
  const hasChildren = Boolean(node.children?.length);
  const expanded = isExpanded(node.id);
  const Icon = ICONS[node.type] ?? Folder;
  const isActive = node.id === activeId;
  const isSelectable = node.type === "chapter";

  const handleClick = () => {
    if (isSelectable) onSelectChapter?.(node.id);
    if (hasChildren) toggleNode(node.id);
  };

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        style={{ paddingLeft: `${12 + level * 16}px` }}
        className={cn(
          "w-full flex items-center gap-1.5 py-1.5 pr-2 rounded-btn text-sm transition-colors text-left",
          isActive
            ? "bg-blue-50 text-primary font-medium"
            : "text-slate-600 hover:bg-slate-50",
        )}
      >
        {hasChildren ? (
          <ChevronRight
            className={cn(
              "w-3.5 h-3.5 shrink-0 text-slate-400 transition-transform",
              expanded && "rotate-90",
            )}
          />
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <Icon
          className={cn(
            "w-4 h-4 shrink-0",
            isActive ? "text-primary" : "text-slate-400",
          )}
        />
        <span className="truncate">{node.name}</span>
      </button>

      {hasChildren && expanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              level={level + 1}
              isExpanded={isExpanded}
              toggleNode={toggleNode}
              activeId={activeId}
              onSelectChapter={onSelectChapter}
            />
          ))}
        </div>
      )}
    </div>
  );
}
