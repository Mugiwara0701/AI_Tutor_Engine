// src/features/topics/pages/TopicDetailPage.jsx

import { useParams } from "react-router-dom";
import { Eye, Sparkles, Upload, Share2 } from "lucide-react";
import { useTopicData } from "../hooks/useTopicData.js";
import TopicHeader from "../components/TopicHeader.jsx";
import TopicTabs from "../components/TopicTabs.jsx";
import OverviewTab from "../components/OverviewTab/OverviewTab.jsx";
import SubTopicOrderTab from "../components/SubTopicOrderTab.jsx";
import MasterPromptTab from "../components/MasterPromptTab.jsx";
import VariablesTab from "../components/VariablesTab.jsx";
import AssetsTab from "../components/AssetsTab.jsx";
import HistoryTab from "../components/HistoryTab.jsx";
import PlaceholderPage from "../../../components/shared/PlaceholderPage.jsx";
import BreadcrumbNav from "../../../layouts/Navbar/BreadcrumbNav.jsx";

const TAB_COMPONENTS = {
  Overview: OverviewTab,
  "Learning Graph": () => (
    <PlaceholderPage title="Learning Graph" phase="Phase 5" />
  ),
  "Sub Topic Order": SubTopicOrderTab,
  "Master Prompt": MasterPromptTab,
  Variables: VariablesTab,
  Assets: AssetsTab,
  History: HistoryTab,
};

export default function TopicDetailPage() {
  const { topicId } = useParams();
  const { topic, isLoading, tabs, activeTab, setActiveTab } =
    useTopicData(topicId);

  if (isLoading || !topic) {
    return <div className="text-sm text-slate-400 p-6">Loading topic…</div>;
  }

  const ActiveTabComponent = TAB_COMPONENTS[activeTab] ?? OverviewTab;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <BreadcrumbNav />

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Eye className="w-4 h-4" />
            See Prompt
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Generate Prompt
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Upload ZIP
          </button>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Share2 className="w-4 h-4" />
            Open Graph
          </button>
        </div>
      </div>

      <TopicHeader topic={topic} />

      <TopicTabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <ActiveTabComponent topic={topic} />
    </div>
  );
}
