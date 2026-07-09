// src/features/topics/components/OverviewTab/OverviewTab.jsx
// Placeholder for OverviewTab — implement component/logic here.

// src/features/topics/components/OverviewTab/OverviewTab.jsx

import { Eye, Sparkles, Share2, Upload, Layers, History } from "lucide-react";
import StatsCards from "./StatsCards.jsx";
import LearningObjectivesList from "./LearningObjectivesList.jsx";
import GeneratedAssetsStatus from "./GeneratedAssetsStatus.jsx";
import PrerequisitesList from "./PrerequisitesList.jsx";
import KeyVariablesTable from "./KeyVariablesTable.jsx";
import RelatedTopicsList from "./RelatedTopicsList.jsx";
import QuickActionsPanel from "../../../../components/shared/QuickActionsPanel.jsx";

export default function OverviewTab({ topic }) {
  if (!topic) return null;

  const quickActions = [
    { label: "View Prompt", icon: Eye },
    { label: "Generate Prompt", icon: Sparkles },
    { label: "Open Learning Graph", icon: Share2 },
    { label: "Upload ZIP", icon: Upload },
    { label: "View Assets", icon: Layers },
    { label: "View History", icon: History },
  ];

  return (
    <div className="flex flex-col gap-5">
      <StatsCards stats={topic.stats} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 flex flex-col gap-5">
          <LearningObjectivesList objectives={topic.learningObjectives} />
          <GeneratedAssetsStatus assets={topic.generatedAssets} />
        </div>

        <div className="flex flex-col gap-5">
          <QuickActionsPanel actions={quickActions} />
          <PrerequisitesList prerequisites={topic.prerequisites} />
          <KeyVariablesTable variables={topic.keyVariables} />
          <RelatedTopicsList topics={topic.relatedTopics} />
        </div>
      </div>
    </div>
  );
}
