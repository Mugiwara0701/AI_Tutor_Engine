// src/features/ingestion/components/UploadNewBookModal.jsx
//
// Frontend-only "Upload New Book" flow. No file is ever sent anywhere —
// selecting Upload Book simulates progress with local state and adds a
// new row to the Upload History table.

import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import ProgressBar from "../../../components/ui/ProgressBar.jsx";
import FileDropZone from "./FileDropZone.jsx";
import { useUploadNewBook } from "../hooks/useUploadNewBook.js";

function Field({ label, htmlFor, error, children }) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="block text-sm font-medium text-slate-700 mb-1.5"
      >
        {label}
      </label>
      {children}
      {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
    </div>
  );
}

export default function UploadNewBookModal({ open, onClose, onUploaded }) {
  const {
    form,
    setField,
    boardOptions,
    classOptions,
    subjectOptions,
    bookOptions,
    curriculumYearOptions,
    file,
    fileError,
    fieldErrors,
    isDragging,
    isUploading,
    uploadProgress,
    isFormComplete,
    handleFileInputChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeFile,
    submitUpload,
    reset,
  } = useUploadNewBook({
    onComplete: (entry) => {
      onUploaded(entry);
    },
  });

  const handleClose = () => {
    if (isUploading) return;
    reset();
    onClose();
  };

  return (
    <ModalDialog
      open={open}
      onClose={handleClose}
      title="Upload New Book"
      maxWidth="2xl"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitUpload();
        }}
        noValidate
        className="flex flex-col gap-5"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field
                label="Board"
                htmlFor="upload-board"
                error={fieldErrors.board}
              >
                <Dropdown
                  value={form.board}
                  onChange={(v) => setField("board", v)}
                  options={boardOptions}
                  placeholder="Select board"
                />
              </Field>

              <Field
                label="Class"
                htmlFor="upload-class"
                error={fieldErrors.class}
              >
                <Dropdown
                  value={form.class}
                  onChange={(v) => setField("class", v)}
                  options={classOptions}
                  placeholder={
                    form.board ? "Select class" : "Select a board first"
                  }
                  disabled={!form.board}
                />
              </Field>

              <Field
                label="Subject"
                htmlFor="upload-subject"
                error={fieldErrors.subject}
              >
                <Dropdown
                  value={form.subject}
                  onChange={(v) => setField("subject", v)}
                  options={subjectOptions}
                  placeholder={
                    form.class ? "Select subject" : "Select a class first"
                  }
                  disabled={!form.class}
                />
              </Field>
            </div>

            <Field label="Book" htmlFor="upload-book" error={fieldErrors.book}>
              <Dropdown
                value={form.book}
                onChange={(v) => setField("book", v)}
                options={bookOptions}
                placeholder={
                  form.subject ? "Select book" : "Select a subject first"
                }
                disabled={!form.subject}
              />
              <p className="text-xs text-slate-400 mt-1.5">
                Books are loaded from the catalogue
              </p>
            </Field>

            <Field
              label="Curriculum Year"
              htmlFor="upload-year"
              error={fieldErrors.curriculumYear}
            >
              <Dropdown
                value={form.curriculumYear}
                onChange={(v) => setField("curriculumYear", v)}
                options={curriculumYearOptions}
                placeholder="Select year"
              />
            </Field>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-slate-700">
              Upload Book ZIP
            </label>
            <FileDropZone
              file={file}
              error={fileError}
              isDragging={isDragging}
              onFileInputChange={handleFileInputChange}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onRemove={removeFile}
              helperText="Only ZIP files are allowed. Max size: 2 GB."
            />

            {isUploading && (
              <ProgressBar
                value={uploadProgress}
                label="Uploading…"
                color="primary"
                className="mt-2"
              />
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={handleClose}
            disabled={isUploading}
            className="px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!isFormComplete || isUploading}
            className="px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-primary"
          >
            {isUploading ? "Uploading…" : "Upload Book"}
          </button>
        </div>
      </form>
    </ModalDialog>
  );
}
