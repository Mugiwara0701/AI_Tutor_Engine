// src/features/sub-topic-order/components/EditSubTopicModal.jsx

import { useEffect, useState } from "react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";

const RELATIONS = ["Prerequisite", "Core Concept", "Important"];

export default function EditSubTopicModal({ subTopic, onClose, onSave }) {
  const [form, setForm] = useState({
    name: "",
    estimatedSlides: 0,
    estimatedDurationMinutes: 0,
    relation: RELATIONS[0],
  });

  useEffect(() => {
    if (subTopic) {
      setForm({
        name: subTopic.name,
        estimatedSlides: subTopic.estimatedSlides,
        estimatedDurationMinutes: subTopic.estimatedDurationMinutes,
        relation: subTopic.relation,
      });
    }
  }, [subTopic]);

  if (!subTopic) return null;

  function handleSubmit(e) {
    e.preventDefault();
    onSave(subTopic.id, {
      name: form.name.trim() || subTopic.name,
      estimatedSlides: Number(form.estimatedSlides) || 0,
      estimatedDurationMinutes: Number(form.estimatedDurationMinutes) || 0,
      relation: form.relation,
    });
  }

  return (
    <ModalDialog
      open={!!subTopic}
      onClose={onClose}
      title="Edit Sub Topic"
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1.5">
            Sub Topic Name
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="w-full px-3 py-2 rounded-btn border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Estimated Slides
            </label>
            <input
              type="number"
              min="0"
              value={form.estimatedSlides}
              onChange={(e) =>
                setForm((f) => ({ ...f, estimatedSlides: e.target.value }))
              }
              className="w-full px-3 py-2 rounded-btn border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1.5">
              Duration (minutes)
            </label>
            <input
              type="number"
              min="0"
              value={form.estimatedDurationMinutes}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  estimatedDurationMinutes: e.target.value,
                }))
              }
              className="w-full px-3 py-2 rounded-btn border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1.5">
            Relation to Main Topic
          </label>
          <select
            value={form.relation}
            onChange={(e) =>
              setForm((f) => ({ ...f, relation: e.target.value }))
            }
            className="w-full px-3 py-2 rounded-btn border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
          >
            {RELATIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Save Changes
          </button>
        </div>
      </form>
    </ModalDialog>
  );
}
