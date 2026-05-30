export type NodeType = "blur" | "noise" | "make_mask" | "hf_image_to_image";

export type BlurNode = {
  id: string;
  type: "blur";
  branch: string;
  params: { radius: number; maskNodeId?: string };
};

export type NoiseNode = {
  id: string;
  type: "noise";
  branch: string;
  params: { intensity: number; seed?: number; maskNodeId?: string };
};

export type MakeMaskNode = {
  id: string;
  type: "make_mask";
  branch: string;
  params: { threshold: number; invert: boolean };
};

export type HfImageToImageNode = {
  id: string;
  type: "hf_image_to_image";
  branch: string;
  params: {
    model: string;
    prompt: string;
    provider?: string;
    maskNodeId?: string;
    debug?: boolean;
  };
};

export type PipelineNode = BlurNode | NoiseNode | MakeMaskNode | HfImageToImageNode;

/** branch name → `"original"` (uploaded image) or a pipeline node id that runs before this branch */
export type BranchSources = Record<string, string>;
