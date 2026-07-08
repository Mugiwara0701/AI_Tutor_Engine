// src/features/library/components/LibraryStatsRow.jsx
// Placeholder for LibraryStatsRow — implement component/logic here.

// src/features/library/components/LibraryStatsRow.jsx

import {
  BookOpen,
  Layers,
  GitBranch,
  Lightbulb,
  Image,
  Table2,
} from "lucide-react";
import MetricCard from "../../../components/ui/MetricCard.jsx";

export default function LibraryStatsRow({ stats }) {
  const items = [
    {
      key: "chapters",
      label: "Chapters",
      value: stats.chapters,
      icon: BookOpen,
    },
    {
      key: "mainTopics",
      label: "Main Topics",
      value: stats.mainTopics,
      icon: Layers,
    },
    {
      key: "subTopics",
      label: "Sub Topics",
      value: stats.subTopics,
      icon: GitBranch,
    },
    {
      key: "concepts",
      label: "Concepts",
      value: stats.concepts,
      icon: Lightbulb,
    },
    { key: "figures", label: "Figures", value: stats.figures, icon: Image },
    { key: "tables", label: "Tables", value: stats.tables, icon: Table2 },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {items.map((item) => (
        <MetricCard
          key={item.key}
          icon={item.icon}
          label={item.label}
          value={item.value}
        />
      ))}
    </div>
  );
}
