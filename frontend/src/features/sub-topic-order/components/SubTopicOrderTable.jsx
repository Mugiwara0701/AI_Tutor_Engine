// src/features/sub-topic-order/components/SubTopicOrderTable.jsx
// Placeholder for SubTopicOrderTable — implement component/logic here.

// src/features/sub-topic-order/components/SubTopicOrderTable.jsx

import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { ListOrdered } from "lucide-react";
import SortableRow from "./SortableRow.jsx";
import EmptyState from "../../../components/ui/EmptyState.jsx";

const HEADERS = [
  { label: "", width: "w-10" },
  { label: "Order", width: "w-14" },
  { label: "Sub Topic" },
  { label: "Est. Slides" },
  { label: "Est. Duration" },
  { label: "Relation to Main Topic" },
  { label: "", align: "text-right" },
];

export default function SubTopicOrderTable({
  subTopics,
  onDragEnd,
  onEdit,
  onDelete,
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  if (subTopics.length === 0) {
    return (
      <div className="bg-white border border-slate-100 rounded-card">
        <EmptyState
          icon={ListOrdered}
          title="No sub topics yet"
          description="Sub topics you add to this topic will appear here for reordering."
        />
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-xs font-medium text-slate-400 uppercase tracking-wide">
              {HEADERS.map((h, i) => (
                <th
                  key={i}
                  className={`py-3 pr-4 ${h.width ?? ""} ${h.align ?? ""}`}
                >
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={subTopics.map((s) => s.id)}
              strategy={verticalListSortingStrategy}
            >
              <tbody>
                {subTopics.map((subTopic) => (
                  <SortableRow
                    key={subTopic.id}
                    subTopic={subTopic}
                    onEdit={onEdit}
                    onDelete={onDelete}
                  />
                ))}
              </tbody>
            </SortableContext>
          </DndContext>
        </table>
      </div>

      <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-400">
        Total Sub Topics:{" "}
        <span className="font-medium text-slate-600">{subTopics.length}</span>
      </div>
    </div>
  );
}
