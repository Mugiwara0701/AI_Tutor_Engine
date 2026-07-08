// src/features/prompt-studio/pages/PromptStudioPage.jsx
// Placeholder for PromptStudioPage — implement component/logic here.

// src/features/prompt-studio/pages/PromptStudioPage.jsx

import { useState } from "react";
import { GitCompare, Copy, Check, PlayCircle } from "lucide-react";
import { usePromptData } from "../hooks/usePromptData.js";
import PromptEditorToolbar from "../components/PromptEditorToolbar.jsx";
import PromptEditor from "../components/PromptEditor.jsx";
import VersionHistoryTable from "../components/VersionHistoryTable.jsx";
import PromptInfoCard from "../components/PromptInfoCard.jsx";
import PromptVariablesList from "../components/PromptVariablesList.jsx";
import CompareVersionsModal from "../components/CompareVersionsModal.jsx";
import TestPromptModal from "../components/TestPromptModal.jsx";

export default function PromptStudioPage() {
  const {
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
  } = usePromptData();

  const [compareOpen, setCompareOpen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);

  if (isLoading || !prompt) {
    return <div className="text-sm text-slate-400 p-6">Loading prompt…</div>;
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Master Prompt Viewer
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            View, compare, and test the master prompt used to generate content
            for {prompt.topicName}.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCompareOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <GitCompare className="w-4 h-4" />
            Compare Versions
          </button>
          <button
            type="button"
            onClick={copyPrompt}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            {copyStatus === "copied" ? (
              <Check className="w-4 h-4 text-green-500" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
            {copyStatus === "copied" ? "Copied" : "Copy Prompt"}
          </button>
          <button
            type="button"
            onClick={() => setTestOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <PlayCircle className="w-4 h-4" />
            Test Prompt
          </button>
        </div>
      </div>

      <PromptEditorToolbar
        filters={filters}
        filterOptions={{
          masterPromptOptions: prompt.masterPromptOptions,
          languageOptions: prompt.languageOptions,
          modelOptions: prompt.modelOptions,
        }}
        onChange={updateFilter}
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 items-start">
        <div className="xl:col-span-2 flex flex-col gap-5">
          <PromptEditor
            content={selectedVersion?.content ?? ""}
            stats={stats}
            updatedOn={selectedVersion?.updatedOn}
            updatedBy={selectedVersion?.updatedBy}
            revertedNotice={revertedNotice}
          />
          <VersionHistoryTable
            versions={prompt.versions}
            activeVersion={selectedVersion}
            onView={viewVersion}
            onRevert={revertToVersion}
          />
        </div>

        <div className="flex flex-col gap-5">
          <PromptInfoCard prompt={prompt} />
          <PromptVariablesList variables={prompt.variables} />
        </div>
      </div>

      <CompareVersionsModal
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        versions={prompt.versions}
      />
      <TestPromptModal
        open={testOpen}
        onClose={() => setTestOpen(false)}
        promptContent={selectedVersion?.content ?? ""}
      />
    </div>
  );
}
