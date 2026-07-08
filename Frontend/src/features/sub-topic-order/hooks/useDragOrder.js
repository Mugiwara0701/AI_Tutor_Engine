// src/features/sub-topic-order/hooks/useDragOrder.js

import { useCallback, useMemo, useState } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import mockData from "../data/mockSubTopics.json";

const RELATION_PRIORITY = {
  Prerequisite: 0,
  "Core Concept": 1,
  Important: 2,
};

function withOrder(list) {
  return list.map((item, index) => ({ ...item, order: index + 1 }));
}

/**
 * Manages drag-and-drop reordering, editing, deleting, auto-ordering, and
 * saving for the Sub Topic Order table. Swap saveOrder's setTimeout for a
 * real mutation once the backend is connected — the return shape stays the same.
 */
export function useDragOrder() {
  const [subTopics, setSubTopics] = useState(() =>
    withOrder(mockData.subTopics),
  );
  const [originalOrder, setOriginalOrder] = useState(() =>
    mockData.subTopics.map((s) => s.id),
  );
  const [editingSubTopic, setEditingSubTopic] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);

  const isDirty = useMemo(
    () => subTopics.map((s) => s.id).join(",") !== originalOrder.join(","),
    [subTopics, originalOrder],
  );

  const handleDragEnd = useCallback((event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    setSubTopics((prev) => {
      const oldIndex = prev.findIndex((s) => s.id === active.id);
      const newIndex = prev.findIndex((s) => s.id === over.id);
      return withOrder(arrayMove(prev, oldIndex, newIndex));
    });
  }, []);

  const saveOrder = useCallback(() => {
    setIsSaving(true);
    setTimeout(() => {
      setOriginalOrder(subTopics.map((s) => s.id));
      setIsSaving(false);
      setSavedAt(new Date());
    }, 500);
  }, [subTopics]);

  const autoOrder = useCallback(() => {
    setSubTopics((prev) =>
      withOrder(
        [...prev].sort(
          (a, b) =>
            (RELATION_PRIORITY[a.relation] ?? 99) -
            (RELATION_PRIORITY[b.relation] ?? 99),
        ),
      ),
    );
  }, []);

  const deleteSubTopic = useCallback((id) => {
    setSubTopics((prev) => withOrder(prev.filter((s) => s.id !== id)));
  }, []);

  const updateSubTopic = useCallback((id, patch) => {
    setSubTopics((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
    setEditingSubTopic(null);
  }, []);

  return {
    topic: mockData.topic,
    subTopics,
    isDirty,
    isSaving,
    savedAt,
    editingSubTopic,
    setEditingSubTopic,
    handleDragEnd,
    saveOrder,
    autoOrder,
    deleteSubTopic,
    updateSubTopic,
  };
}
