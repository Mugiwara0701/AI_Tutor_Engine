// src/features/ingestion/hooks/useUploadNewBook.js
//
// Frontend-only state + logic for the "Upload New Book" modal:
// dependent Board -> Class -> Subject -> Book dropdowns (backed by the
// local NCERT catalogue file), file selection/validation, and a simulated
// upload progress sequence. No network calls are made anywhere here.

import { useState } from "react";
import {
  BOARD_OPTIONS,
  CURRICULUM_YEAR_OPTIONS,
  getBookOptions,
  getClassOptions,
  getSubjectOptions,
} from "../data/ncertCatalogue.js";

const EMPTY_FORM = {
  board: "",
  class: "",
  subject: "",
  book: "",
  curriculumYear: "",
};

const MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024 * 1024; // 2 GB
const ALLOWED_EXTENSIONS = [".zip"];

function validateFile(file) {
  if (!file) return "Please select a file to upload.";
  const isAllowedType = ALLOWED_EXTENSIONS.some((ext) =>
    file.name.toLowerCase().endsWith(ext),
  );
  if (!isAllowedType) return "Only ZIP files are allowed.";
  if (file.size > MAX_FILE_SIZE_BYTES) return "File must be 2 GB or smaller.";
  return null;
}

export function useUploadNewBook({ onComplete } = {}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const classOptions = getClassOptions(form.board);
  const subjectOptions = getSubjectOptions(form.board, form.class);
  const bookOptions = getBookOptions(form.board, form.class, form.subject);

  const reset = () => {
    setForm(EMPTY_FORM);
    setFile(null);
    setFileError(null);
    setFieldErrors({});
    setIsDragging(false);
    setIsUploading(false);
    setUploadProgress(0);
  };

  const setField = (key, value) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      // Dependent-dropdown reset behaviour.
      if (key === "board") {
        next.class = "";
        next.subject = "";
        next.book = "";
      } else if (key === "class") {
        next.subject = "";
        next.book = "";
      } else if (key === "subject") {
        next.book = "";
      }
      return next;
    });
    setFieldErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const applyFile = (candidate) => {
    const error = validateFile(candidate);
    setFileError(error);
    setFile(error ? null : candidate);
  };

  const handleFileInputChange = (e) => {
    const selected = e.target.files?.[0] ?? null;
    if (selected) applyFile(selected);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0] ?? null;
    if (dropped) applyFile(dropped);
  };

  const removeFile = () => {
    setFile(null);
    setFileError(null);
  };

  const isFormComplete =
    Boolean(form.board) &&
    Boolean(form.class) &&
    Boolean(form.subject) &&
    Boolean(form.book) &&
    Boolean(form.curriculumYear) &&
    Boolean(file) &&
    !fileError;

  const validateAll = () => {
    const errors = {};
    if (!form.board) errors.board = "Board is required.";
    if (!form.class) errors.class = "Class is required.";
    if (!form.subject) errors.subject = "Subject is required.";
    if (!form.book) errors.book = "Book is required.";
    if (!form.curriculumYear)
      errors.curriculumYear = "Curriculum year is required.";
    setFieldErrors(errors);
    if (!file) setFileError((prev) => prev ?? "Please select a file to upload.");
    return Object.keys(errors).length === 0 && Boolean(file) && !fileError;
  };

  // Simulates an upload: no network call, just a fake progress ramp that
  // resolves after a short delay so the UI can show a loading state.
  const submitUpload = () => {
    if (!validateAll() || !isFormComplete) return;

    setIsUploading(true);
    setUploadProgress(0);

    const steps = [15, 35, 55, 75, 92, 100];
    let stepIndex = 0;

    const interval = setInterval(() => {
      setUploadProgress(steps[stepIndex]);
      stepIndex += 1;
      if (stepIndex >= steps.length) {
        clearInterval(interval);
        setTimeout(() => {
          onComplete?.({ ...form, file });
          reset();
        }, 350);
      }
    }, 220);
  };

  return {
    form,
    setField,
    boardOptions: BOARD_OPTIONS,
    classOptions,
    subjectOptions,
    bookOptions,
    curriculumYearOptions: CURRICULUM_YEAR_OPTIONS,
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
  };
}
