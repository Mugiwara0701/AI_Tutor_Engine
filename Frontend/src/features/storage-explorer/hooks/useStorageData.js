// src/features/storage-explorer/hooks/useStorageData.js
// Placeholder for useStorageData — implement component/logic here.

// src/features/storage-explorer/hooks/useStorageData.js

import { useCallback, useMemo, useState } from "react";
import mockStorage from "../data/mockStorage.json";

function countFolders(node) {
  if (!node.children?.length) return 1;
  return 1 + node.children.reduce((sum, child) => sum + countFolders(child), 0);
}

export function useStorageData() {
  const [activeFolderId, setActiveFolderId] = useState(
    mockStorage.activeFolderId,
  );
  const [expandedNodes, setExpandedNodes] = useState(
    new Set(["root", "class-12", "physics", "physics-part-1"]),
  );
  const [viewMode, setViewMode] = useState("list");
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState([]);

  const toggleNode = useCallback((nodeId) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      next.has(nodeId) ? next.delete(nodeId) : next.add(nodeId);
      return next;
    });
  }, []);

  const isExpanded = useCallback(
    (nodeId) => expandedNodes.has(nodeId),
    [expandedNodes],
  );

  const files = useMemo(
    () => mockStorage.filesByFolder[activeFolderId] ?? [],
    [activeFolderId],
  );

  const breadcrumb = useMemo(
    () => mockStorage.breadcrumbsByFolder[activeFolderId] ?? [],
    [activeFolderId],
  );

  const stats = useMemo(() => {
    const totalSizeBytes = files.reduce((sum, f) => sum + f.sizeBytes, 0);
    const fileTypes = new Set(files.map((f) => f.type)).size;
    const lastModified = files.reduce(
      (latest, f) =>
        !latest || new Date(f.modified) > new Date(latest)
          ? f.modified
          : latest,
      null,
    );

    return {
      totalFiles: files.length,
      totalFolders: countFolders(mockStorage.tree) - 1, // exclude root itself
      totalSizeBytes,
      fileTypes,
      lastModified,
    };
  }, [files]);

  return {
    tree: mockStorage.tree,
    storage: mockStorage.storage,
    isExpanded,
    toggleNode,
    activeFolderId,
    setActiveFolderId,
    breadcrumb,
    files,
    stats,
    viewMode,
    setViewMode,
    pageSize,
    setPageSize,
    selectedIds,
    setSelectedIds,
  };
}
