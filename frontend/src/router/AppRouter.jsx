// src/router/AppRouter.jsx

import { Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "../features/auth/pages/LoginPage.jsx";
import SignUpPage from "../features/auth/pages/SignUpPage.jsx";
import DashboardPage from "../features/dashboard/pages/DashboardPage.jsx";
import LibraryPage from "../features/library/pages/LibraryPage.jsx";
import LearningGraphPage from "../features/learning-graph/pages/LearningGraphPage.jsx";
import PromptStudioPage from "../features/prompt-studio/pages/PromptStudioPage.jsx";
import IngestionPage from "../features/ingestion/pages/IngestionPage.jsx";
import ZipManagerPage from "../features/zip-manager/pages/ZipManagerPage.jsx";
import PipelineMonitorPage from "../features/pipeline-monitor/pages/PipelineMonitorPage.jsx";
import StorageExplorerPage from "../features/storage-explorer/pages/StorageExplorerPage.jsx";
import AnalyticsPage from "../features/analytics/pages/AnalyticsPage.jsx";
import GlobalSearchPage from "../features/global-search/pages/GlobalSearchPage.jsx";
import SettingsPage from "../features/settings/pages/SettingsPage.jsx";
import DashboardLayout from "../layouts/DashboardLayout.jsx";
import ProtectedRoute from "./ProtectedRoute.jsx";
import TopicDetailPage from "../features/topics/pages/TopicDetailPage.jsx";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignUpPage />} />

      <Route
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />

        <Route path="/library" element={<LibraryPage />} />
        {/* <Route path="/library/board/cbse" element={<LibraryPage />} /> */}
        <Route path="/library/topics/:topicId" element={<TopicDetailPage />} />

        <Route path="/learning-graph" element={<LearningGraphPage />} />
        <Route path="/prompt-studio" element={<PromptStudioPage />} />
        <Route path="/ingestion" element={<IngestionPage />} />
        <Route path="/zip-manager" element={<ZipManagerPage />} />
        <Route path="/pipeline-monitor" element={<PipelineMonitorPage />} />
        <Route path="/storage-explorer" element={<StorageExplorerPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/search" element={<GlobalSearchPage />} />
        <Route path="/employee" element={<SettingsPage />} />
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
