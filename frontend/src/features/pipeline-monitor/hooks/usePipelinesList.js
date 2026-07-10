// src/features/pipeline-monitor/hooks/usePipelinesList.js

import { useState } from "react";
import mockPipelinesList from "../data/mockPipelinesList.json";

export function usePipelinesList() {
  const [pipelines, setPipelines] = useState(mockPipelinesList.pipelines);

  const startPipeline = (id) => {
    setPipelines((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "Active" } : p)),
    );
  };

  const pausePipeline = (id) => {
    setPipelines((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "Paused" } : p)),
    );
  };

  const togglePipeline = (id) => {
    setPipelines((prev) =>
      prev.map((p) =>
        p.id === id
          ? { ...p, status: p.status === "Active" ? "Paused" : "Active" }
          : p,
      ),
    );
  };

  const startAll = () => {
    setPipelines((prev) => prev.map((p) => ({ ...p, status: "Active" })));
  };

  const pauseAll = () => {
    setPipelines((prev) => prev.map((p) => ({ ...p, status: "Paused" })));
  };

  return {
    pipelines,
    startPipeline,
    pausePipeline,
    togglePipeline,
    startAll,
    pauseAll,
  };
}
