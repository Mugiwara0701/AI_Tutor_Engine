// src/features/zip-manager/components/TopicZipUploadModal.jsx
//
// Frontend-only upload form. No file is actually sent anywhere — only its
// name is captured into local state so the UI flow can be demonstrated.

import { useEffect, useRef, useState } from "react";
import { FileArchive, UploadCloud, X } from "lucide-react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import { cn } from "../../../utils/classNames.js";

const EMPTY_FORM = {
  class: "",
  subject: "",
  chapter: "",
  topicName: "",
};

function validate(form, file) {
  const errors = {};
  if (!form.class) errors.class = "Class is required.";
  if (!form.subject) errors.subject = "Subject is required.";
  if (!form.chapter) errors.chapter = "Chapter is required.";
  if (!form.topicName.trim()) errors.topicName = "Topic name is required.";
  if (!file) {
    errors.file = "A ZIP file is required.";
  } else if (!file.name.toLowerCase().endsWith(".zip")) {
    errors.file = "Only .zip files are allowed.";
  }
  return errors;
}

export default function TopicZipUploadModal({
  open,
  onClose,
  onSubmit,
  classOptions,
  subjectOptions,
  chapterOptions,
  topicsByChapter,
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState({});
  const fileInputRef = useRef(null);

  const topicOptions = form.chapter
    ? (topicsByChapter[form.chapter] ?? [])
    : [];

  useEffect(() => {
    if (!open) return;
    setForm(EMPTY_FORM);
    setFile(null);
    setErrors({});
  }, [open]);

  const setField = (key, value) => {
    setForm((prev) => ({
      ...prev,
      [key]: value,
      ...(key === "chapter" ? { topicName: "" } : {}),
    }));
    setErrors((prev) => ({
      ...prev,
      [key]: undefined,
      ...(key === "chapter" ? { topicName: undefined } : {}),
    }));
  };

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setErrors((prev) => ({ ...prev, file: undefined }));
  };

  const handleReset = () => {
    setForm(EMPTY_FORM);
    setFile(null);
    setErrors({});
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const nextErrors = validate(form, file);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    onSubmit({ ...form, fileName: file.name });
  };

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Upload Topic-wise ZIP"
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Class
            </label>
            <Dropdown
              value={form.class}
              onChange={(v) => setField("class", v)}
              options={classOptions}
              placeholder="Select class"
            />
            {errors.class && (
              <p className="text-xs text-red-600 mt-1">{errors.class}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Subject
            </label>
            <Dropdown
              value={form.subject}
              onChange={(v) => setField("subject", v)}
              options={subjectOptions}
              placeholder="Select subject"
            />
            {errors.subject && (
              <p className="text-xs text-red-600 mt-1">{errors.subject}</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Chapter
          </label>
          <Dropdown
            value={form.chapter}
            onChange={(v) => setField("chapter", v)}
            options={chapterOptions}
            placeholder="Select chapter"
          />
          {errors.chapter && (
            <p className="text-xs text-red-600 mt-1">{errors.chapter}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Topic Name
          </label>
          <Dropdown
            value={form.topicName}
            onChange={(v) => setField("topicName", v)}
            options={topicOptions}
            placeholder={
              form.chapter ? "Select topic" : "Select a chapter first"
            }
            disabled={!form.chapter}
          />
          {errors.topicName && (
            <p className="text-xs text-red-600 mt-1">{errors.topicName}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            ZIP File
          </label>

          {file ? (
            <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-btn border border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2 min-w-0">
                <FileArchive className="w-4 h-4 text-primary shrink-0" />
                <span className="text-sm text-slate-700 truncate">
                  {file.name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
                className="p-1 rounded hover:bg-slate-200 transition-colors shrink-0"
                aria-label="Remove file"
              >
                <X className="w-3.5 h-3.5 text-slate-500" />
              </button>
            </div>
          ) : (
            <label
              className={cn(
                "flex flex-col items-center justify-center gap-1.5 px-4 py-6 rounded-btn border border-dashed cursor-pointer transition-colors",
                errors.file
                  ? "border-red-300 bg-red-50/40"
                  : "border-slate-300 hover:border-primary/40 hover:bg-bgBlueTint/40",
              )}
            >
              <UploadCloud className="w-5 h-5 text-slate-400" />
              <span className="text-sm text-slate-500">
                Click to select a .zip file
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                onChange={handleFileChange}
                className="hidden"
              />
            </label>
          )}
          {errors.file && (
            <p className="text-xs text-red-600 mt-1">{errors.file}</p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={handleReset}
            className="px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Reset
          </button>
          <button
            type="submit"
            className="px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Upload ZIP
          </button>
        </div>
      </form>
    </ModalDialog>
  );
}
