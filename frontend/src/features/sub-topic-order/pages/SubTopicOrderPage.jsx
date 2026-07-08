// src/features/sub-topic-order/pages/SubTopicOrderPage.jsx
// Placeholder for SubTopicOrderPage — implement component/logic here.

// src/features/sub-topic-order/pages/SubTopicOrderPage.jsx

import { Save, Check } from "lucide-react";
import { useDragOrder } from "../hooks/useDragOrder.js";
import SubTopicOrderTable from "../components/SubTopicOrderTable.jsx";
import TipsCard from "../components/TipsCard.jsx";
import AutoOrderCard from "../components/AutoOrderCard.jsx";
import EditSubTopicModal from "../components/EditSubTopicModal.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";
import { formatTimeAgo } from "../../../utils/formatDate.js";

export default function SubTopicOrderPage() {
  const {
    topic,
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
  } = useDragOrder();

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Sub Topic Order</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {topic?.name
              ? `Arrange the learning sequence for "${topic.name}."`
              : "Arrange the learning sequence for this topic."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {!isDirty && savedAt && (
            <span className="flex items-center gap-1.5 text-xs text-slate-400">
              <Check className="w-3.5 h-3.5 text-green-500" />
              Saved {formatTimeAgo(savedAt)}
            </span>
          )}
          <button
            type="button"
            onClick={saveOrder}
            disabled={!isDirty || isSaving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Save className="w-4 h-4" />
            {isSaving ? "Saving…" : "Save Order"}
          </button>
          <ActionMenu
            items={[
              { label: "Export order as CSV", onClick: () => {} },
              { label: "Reset to last saved", onClick: () => {} },
            ]}
          />
        </div>
      </div>

      <div className="flex items-start gap-2.5 bg-bgBlueTint border border-blue-100 rounded-card px-4 py-3">
        <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
        <p className="text-sm text-blue-800">
          Drag and drop sub topics to reorder them. The new order will be
          followed in the learning path and content generation.
        </p>
      </div>

      <SubTopicOrderTable
        subTopics={subTopics}
        onDragEnd={handleDragEnd}
        onEdit={setEditingSubTopic}
        onDelete={deleteSubTopic}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <TipsCard />
        <AutoOrderCard onAutoOrder={autoOrder} />
      </div>

      <EditSubTopicModal
        subTopic={editingSubTopic}
        onClose={() => setEditingSubTopic(null)}
        onSave={updateSubTopic}
      />
    </div>
  );
}
