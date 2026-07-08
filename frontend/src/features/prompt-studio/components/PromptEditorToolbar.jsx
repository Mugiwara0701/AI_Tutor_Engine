// src/features/prompt-studio/components/PromptEditorToolbar.jsx
// Placeholder for PromptEditorToolbar — implement component/logic here.
// src/features/prompt-studio/components/PromptEditorToolbar.jsx

import Dropdown from "../../../components/ui/Dropdown.jsx";

export default function PromptEditorToolbar({
  filters,
  filterOptions,
  onChange,
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 bg-white border border-slate-100 rounded-card px-4 py-3">
      <Dropdown
        label="Master Prompt"
        value={filters.masterPrompt}
        onChange={(v) => onChange("masterPrompt", v)}
        options={filterOptions.masterPromptOptions}
        className="w-full sm:w-56"
      />
      <Dropdown
        label="Language"
        value={filters.language}
        onChange={(v) => onChange("language", v)}
        options={filterOptions.languageOptions}
        className="w-full sm:w-40"
      />
      <Dropdown
        label="Model"
        value={filters.model}
        onChange={(v) => onChange("model", v)}
        options={filterOptions.modelOptions}
        className="w-full sm:w-44"
      />
    </div>
  );
}
