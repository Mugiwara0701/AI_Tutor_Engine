// src/features/prompt-studio/components/PromptInfoCard.jsx
// Placeholder for PromptInfoCard — implement component/logic here.

// src/features/prompt-studio/components/PromptInfoCard.jsx

import VersionBadge from "../../../components/ui/VersionBadge.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import { formatDate } from "../../../utils/formatDate.js";

function InfoRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-slate-50 last:border-b-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-sm font-medium text-slate-700">{children}</span>
    </div>
  );
}

export default function PromptInfoCard({ prompt }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5">
      <p className="text-sm font-semibold text-slate-800 mb-1">
        Prompt Information
      </p>
      <div>
        <InfoRow label="Prompt Type">{prompt.type}</InfoRow>
        <InfoRow label="Version">
          <VersionBadge version={prompt.currentVersion} isLatest />
        </InfoRow>
        <InfoRow label="Created On">{formatDate(prompt.createdOn)}</InfoRow>
        <InfoRow label="Last Updated">{formatDate(prompt.lastUpdated)}</InfoRow>
        <InfoRow label="Updated By">
          <UserAvatar name={prompt.updatedBy?.name} size="sm" showDetails />
        </InfoRow>
        <InfoRow label="Status">
          <StatusBadge status={prompt.status} />
        </InfoRow>
        <InfoRow label="Model">{prompt.model}</InfoRow>
        <InfoRow label="Language">{prompt.language}</InfoRow>
      </div>
    </div>
  );
}
