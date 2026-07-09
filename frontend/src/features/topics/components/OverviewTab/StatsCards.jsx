// src/features/topics/components/OverviewTab/StatsCards.jsx
// Placeholder for StatsCards — implement component/logic here.

// src/features/topics/components/OverviewTab/StatsCards.jsx

import { BookOpen, Presentation, Clock, Gauge, Flag } from "lucide-react";
import MetricCard from "../../../../components/ui/MetricCard.jsx";
import { formatDuration } from "../../../../utils/formatDuration.js";

export default function StatsCards({ stats }) {
  if (!stats) return null;

  const cards = [
    { icon: BookOpen, label: "Concepts", value: stats.concepts },
    {
      icon: Presentation,
      label: "Estimated Slides",
      value: stats.estimatedSlides,
    },
    {
      icon: Clock,
      label: "Learning Time",
      value: formatDuration(stats.learningTimeMinutes),
    },
    { icon: Gauge, label: "Difficulty", value: stats.difficulty },
    { icon: Flag, label: "Importance", value: stats.importance },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      {cards.map((card) => (
        <MetricCard key={card.label} {...card} />
      ))}
    </div>
  );
}
