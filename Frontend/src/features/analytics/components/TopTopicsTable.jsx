// src/features/analytics/components/TopTopicsTable.jsx
// Placeholder for TopTopicsTable — implement component/logic here.

// src/features/analytics/components/TopTopicsTable.jsx

import SparklineChart from "../../../components/ui/SparklineChart.jsx";

export default function TopTopicsTable({ topics = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-50">
        <h3 className="text-sm font-semibold text-slate-800">
          Top Topics by Activity
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-400 border-b border-slate-50">
              <th className="px-5 py-3 font-medium w-10">#</th>
              <th className="px-5 py-3 font-medium">Topic</th>
              <th className="px-5 py-3 font-medium">Generations</th>
              <th className="px-5 py-3 font-medium">Success Rate</th>
              <th className="px-5 py-3 font-medium">Avg. Time</th>
              <th className="px-5 py-3 font-medium">Avg. Slides</th>
              <th className="px-5 py-3 font-medium">Trend</th>
            </tr>
          </thead>
          <tbody>
            {topics.map((topic) => (
              <tr
                key={topic.rank}
                className="border-b border-slate-50 last:border-b-0"
              >
                <td className="px-5 py-3 text-slate-400">{topic.rank}</td>
                <td className="px-5 py-3 font-medium text-slate-800">
                  {topic.topic}
                </td>
                <td className="px-5 py-3 text-slate-600">
                  {topic.generations}
                </td>
                <td className="px-5 py-3 text-slate-600">
                  {topic.successRate}%
                </td>
                <td className="px-5 py-3 text-slate-600">{topic.avgTime}</td>
                <td className="px-5 py-3 text-slate-600">{topic.avgSlides}</td>
                <td className="px-5 py-3">
                  <SparklineChart data={topic.trend} color="primary" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
