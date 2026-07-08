// src/features/prompt-studio/hooks/usePromptData.js
// Placeholder for usePromptData — implement component/logic here.
// src/features/prompt-studio/hooks/usePromptData.js

import { useEffect, useMemo, useState } from "react";
import mockPrompt from "../data/mockPrompt.json";

function computeStats(content) {
  const characters = content.length;
  const words = content.trim().split(/\s+/).filter(Boolean).length;
  // Rough token estimate: ~4 characters per token
  const tokens = Math.ceil(characters / 4);
  return { tokens, characters, words };
}

/**
 * Loads prompt data (mocked), manages the filter bar, the active version
 * shown in the editor, copy-to-clipboard state, and version revert/view.
 * Swap the setTimeout block for a real fetch once the backend is connected.
 */
export function usePromptData() {
  const [prompt, setPrompt] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [filters, setFilters] = useState({
    masterPrompt: "",
    language: "",
    model: "",
  });
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [copyStatus, setCopyStatus] = useState("idle"); // idle | copied
  const [revertedNotice, setRevertedNotice] = useState(null);

  useEffect(() => {
    setIsLoading(true);
    const timer = setTimeout(() => {
      setPrompt(mockPrompt);
      setFilters({
        masterPrompt: mockPrompt.masterPromptOptions?.[0] ?? "",
        language: mockPrompt.language,
        model: mockPrompt.model,
      });
      setSelectedVersion(
        mockPrompt.versions?.find((v) => v.isLatest) ??
          mockPrompt.versions?.[0],
      );
      setIsLoading(false);
    }, 200);
    return () => clearTimeout(timer);
  }, []);

  const updateFilter = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const stats = useMemo(
    () => computeStats(selectedVersion?.content ?? ""),
    [selectedVersion],
  );

  function viewVersion(version) {
    setSelectedVersion(version);
  }

  function revertToVersion(version) {
    setSelectedVersion(version);
    setRevertedNotice(`Restored editor content from ${version.version}`);
    setTimeout(() => setRevertedNotice(null), 2500);
  }

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(selectedVersion?.content ?? "");
      setCopyStatus("copied");
      setTimeout(() => setCopyStatus("idle"), 1800);
    } catch {
      setCopyStatus("idle");
    }
  }

  return {
    prompt,
    isLoading,
    filters,
    updateFilter,
    selectedVersion,
    viewVersion,
    revertToVersion,
    revertedNotice,
    stats,
    copyStatus,
    copyPrompt,
  };
}
