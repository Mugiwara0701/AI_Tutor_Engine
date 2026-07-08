// src/features/topics/hooks/useTopicData.js
// Placeholder for useTopicData — implement component/logic here.

// src/features/topics/hooks/useTopicData.js

import { useEffect, useState } from "react";
import mockTopic from "../data/mockTopic.json";

const TABS = [
  "Overview",
  "Learning Graph",
  "Sub Topic Order",
  "Master Prompt",
  "Variables",
  "Assets",
  "History",
];

/**
 * Loads topic data (mocked) and manages the active tab for the Topic Detail page.
 * Swap the setTimeout block for a real fetch / React Query call once the
 * backend is connected — the return shape stays the same.
 */
export function useTopicData(topicId) {
  const [topic, setTopic] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(TABS[0]);

  useEffect(() => {
    setIsLoading(true);
    const timer = setTimeout(() => {
      setTopic(mockTopic);
      setIsLoading(false);
    }, 200);
    return () => clearTimeout(timer);
  }, [topicId]);

  return { topic, isLoading, tabs: TABS, activeTab, setActiveTab };
}
