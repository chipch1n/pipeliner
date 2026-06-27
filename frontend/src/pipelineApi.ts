import { requestJson } from "./apiClient";
import type { BranchSources, PipelineNode } from "./pipelineTypes";

export type PipelineListItem = {
  id: number;
  name: string;
};

export type SavedPipeline = {
  id: number;
  name: string;
  pipeline_data: {
    nodes: PipelineNode[];
    branch_sources?: BranchSources;
    branchSources?: BranchSources;
  };
};

export function listPipelines(): Promise<PipelineListItem[]> {
  return requestJson<PipelineListItem[]>("/pipelines", { method: "GET" });
}

export function loadPipeline(name: string): Promise<SavedPipeline> {
  return requestJson<SavedPipeline>(`/pipelines/${encodeURIComponent(name)}`, { method: "GET" });
}

export function savePipeline(
  name: string,
  nodes: PipelineNode[],
  branchSources: BranchSources
): Promise<{ id: number }> {
  return requestJson<{ id: number }>("/pipelines", {
    method: "POST",
    body: JSON.stringify({ name, nodes, branchSources })
  });
}

export function deletePipeline(name: string): Promise<{ message: string }> {
  return requestJson<{ message: string }>(`/pipelines/${encodeURIComponent(name)}`, {
    method: "DELETE"
  });
}
