// src/features/prompt-studio/components/PromptVariablesList.jsx
// Placeholder for PromptVariablesList — implement component/logic here.

// src/features/prompt-studio/components/PromptVariablesList.jsx

export default function PromptVariablesList({ variables }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5">
      <p className="text-sm font-semibold text-slate-800 mb-3">
        Prompt Variables
      </p>
      <ul className="flex flex-col gap-2.5">
        {variables.map((v) => (
          <li key={v.key} className="flex items-start gap-2.5">
            <code className="shrink-0 px-2 py-1 rounded-btn bg-bgBlueTint text-primary text-xs font-mono font-medium">
              {v.key}
            </code>
            <span className="text-sm text-slate-500 pt-0.5">
              {v.description}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
