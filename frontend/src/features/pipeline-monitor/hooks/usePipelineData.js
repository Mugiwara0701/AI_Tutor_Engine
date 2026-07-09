// src/features/pipeline-monitor/hooks/usePipelineData.js
// Placeholder for usePipelineData — implement component/logic here.

// src/features/pipeline-monitor/hooks/usePipelineData.js

import { useEffect, useMemo, useState } from "react";
import mockPipeline from "../data/mockPipeline.json";

/**
 * Loads mock pipeline data and lightly simulates a "live" monitor by
 * nudging the in-progress stage's percentage forward every few seconds.
 * Purely cosmetic — resets to the mock baseline on remount.
 */
export function usePipelineData() {
  const [pipeline, setPipeline] = useState(mockPipeline.pipeline);
  const [stages, setStages] = useState(mockPipeline.stages);

  useEffect(() => {
    const interval = setInterval(() => {
      setStages((prev) =>
        prev.map((stage) => {
          if (stage.status !== "In Progress") return stage;
          const nextProgress = Math.min(99, stage.progress + 1);
          return { ...stage, progress: nextProgress };
        }),
      );
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  const elapsedMinutes = useMemo(() => {
    const started = new Date(pipeline.startedAt).getTime();
    if (Number.isNaN(started)) return 0;
    return Math.max(0, Math.floor((Date.now() - started) / 60000));
  }, [pipeline.startedAt]);

  return {
    pipeline,
    setPipeline,
    stages,
    stats: mockPipeline.stats,
    resources: mockPipeline.resources,
    activityLog: mockPipeline.activityLog,
    elapsedMinutes,
  };
}
