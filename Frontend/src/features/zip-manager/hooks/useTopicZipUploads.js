// src/features/zip-manager/hooks/useTopicZipUploads.js
//
// Frontend-only state for the "Topic-wise ZIP Upload" section. Files are
// never actually uploaded anywhere — only the file name is kept in state.

import { useState } from "react";
import mockTopicZipUploads from "../data/mockTopicZipUploads.json";
import mockZips from "../data/mockZips.json";
import mockTopicsMaster from "../data/mockTopicsMaster.json";

let idCounter = mockTopicZipUploads.uploads.length + 1;

function generateId() {
  return `topic-zip-${idCounter++}`;
}

export function useTopicZipUploads() {
  const [uploads, setUploads] = useState(mockTopicZipUploads.uploads);

  const addUpload = (entry) => {
    const newUpload = {
      id: generateId(),
      uploadDate: new Date().toISOString(),
      ...entry,
    };
    setUploads((prev) => [newUpload, ...prev]);
    return newUpload;
  };

  const replaceFile = (id, fileName) => {
    setUploads((prev) =>
      prev.map((u) =>
        u.id === id
          ? { ...u, fileName, uploadDate: new Date().toISOString() }
          : u,
      ),
    );
  };

  const deleteUpload = (id) => {
    setUploads((prev) => prev.filter((u) => u.id !== id));
  };

  return {
    uploads,
    classOptions: mockZips.filterOptions.classOptions,
    subjectOptions: mockZips.filterOptions.subjectOptions,
    chapterOptions: mockZips.filterOptions.chapterOptions,
    topicsByChapter: mockTopicsMaster.topicsByChapter,
    addUpload,
    replaceFile,
    deleteUpload,
  };
}
