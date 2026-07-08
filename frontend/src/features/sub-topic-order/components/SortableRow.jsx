// src/features/sub-topic-order/components/SortableRow.jsx
// Placeholder for SortableRow — implement component/logic here.

// src/features/sub-topic-order/components/SortableRow.jsx

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Pencil, Trash2 } from "lucide-react";
import DragHandle from "../../../components/ui/DragHandle.jsx";
import RelationBadge from "./RelationBadge.jsx";
import { formatDuration } from "../../../utils/formatDuration.js";
import { cn } from "../../../utils/classNames.js";

export default function SortableRow({ subTopic, onEdit, onDelete }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: subTopic.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-b border-slate-100 last:border-b-0 bg-white",
        isDragging && "relative z-10 shadow-lg",
      )}
    >
      <td className="w-10 pl-4 py-3">
        <DragHandle {...attributes} {...listeners} />
      </td>
      <td className="w-14 py-3">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-bgBlueTint text-primary text-xs font-semibold">
          {subTopic.order}
        </span>
      </td>
      <td className="py-3 pr-4">
        <p className="font-medium text-slate-800">{subTopic.name}</p>
      </td>
      <td className="py-3 pr-4 text-slate-600">{subTopic.estimatedSlides}</td>
      <td className="py-3 pr-4 text-slate-600">
        {formatDuration(subTopic.estimatedDurationMinutes)}
      </td>
      <td className="py-3 pr-4">
        <RelationBadge relation={subTopic.relation} />
      </td>
      <td className="py-3 pr-4">
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={() => onEdit(subTopic)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Edit ${subTopic.name}`}
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => onDelete(subTopic.id)}
            className="p-1.5 rounded-btn text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            aria-label={`Delete ${subTopic.name}`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}
