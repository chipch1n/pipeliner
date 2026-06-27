import type {
  BlurNode,
  BranchSources,
  HfImageToImageNode,
  NoiseNode,
  NodeType,
  PipelineNode
} from "./pipelineTypes";

export const DEFAULT_PROCESS_API_URL = "/api/process-image";

function normalizedBranch(branch: string): string {
  return branch.trim() || "main";
}

export function createNode(type: NodeType): PipelineNode {
  const id = `${type}-${crypto.randomUUID()}`;
  if (type === "blur") {
    return { id, type, branch: "main", params: { radius: 4 } };
  }
  if (type === "noise") {
    return { id, type, branch: "main", params: { intensity: 20, seed: 0 } };
  }
  if (type === "hf_image_to_image") {
    return {
      id,
      type,
      branch: "main",
      params: {
        model: "Qwen/Qwen-Image-Edit",
        prompt: "make cool",
        provider: "replicate",
        debug: true
      }
    };
  }
  return { id, type, branch: "main", params: { threshold: 128, invert: false } };
}

export function applyNodeUpdate(
  prev: PipelineNode[],
  id: string,
  updater: (node: PipelineNode) => PipelineNode
): PipelineNode[] {
  const previousMaskByNodeId = new Map(
    prev
      .filter(
        (n): n is BlurNode | NoiseNode | HfImageToImageNode =>
          n.type === "blur" || n.type === "noise" || n.type === "hf_image_to_image"
      )
      .map((n) => [n.id, n.params.maskNodeId])
  );

  const next = prev.map((n) => (n.id === id ? updater(n) : n));

  return next.map((n): PipelineNode => {
    if (n.type !== "blur" && n.type !== "noise" && n.type !== "hf_image_to_image") return n;
    const prevMask = previousMaskByNodeId.get(n.id);
    if (!prevMask || n.params.maskNodeId) return n;
    return {
      ...n,
      params: { ...n.params, maskNodeId: prevMask }
    };
  });
}

export function removeNodeFromList(prev: PipelineNode[], id: string): PipelineNode[] {
  return prev.filter((n) => n.id !== id);
}

function sameBranch(a: PipelineNode, b: PipelineNode): boolean {
  return normalizedBranch(a.branch) === normalizedBranch(b.branch);
}

/**
 * Swap with the next/previous node on the **same branch** along the flat list (skip nodes on other lanes).
 * So ← → never exchanges with another branch; multiple branches may sit between two slots on one lane.
 */
export function reorderNodesWithinBranch(
  prev: PipelineNode[],
  index: number,
  direction: -1 | 1
): PipelineNode[] {
  const branch = prev[index];
  let j = index + direction;
  while (j >= 0 && j < prev.length && !sameBranch(branch, prev[j])) {
    j += direction;
  }
  if (j < 0 || j >= prev.length) return prev;
  const next = [...prev];
  [next[index], next[j]] = [next[j], next[index]];
  return next;
}

export function canReorderNodeInBranch(
  nodes: PipelineNode[],
  index: number,
  direction: -1 | 1
): boolean {
  const branch = nodes[index];
  let j = index + direction;
  while (j >= 0 && j < nodes.length && !sameBranch(branch, nodes[j])) {
    j += direction;
  }
  return j >= 0 && j < nodes.length;
}

export function maskCapableNodeIds(
  nodes: PipelineNode[],
  branchSources: BranchSources = {}
): Set<string> {
  const ids = new Set<string>();
  let ordered: PipelineNode[];
  try {
    ordered = orderPipelineNodes(nodes, branchSources, false);
  } catch {
    ordered = nodes;
  }

  const branchIsMask = new Map<string, boolean>([["main", false]]);
  for (const node of ordered) {
    const branch = normalizedBranch(node.branch);
    if (!branchIsMask.has(branch)) {
      const src = branchSources[branch];
      branchIsMask.set(branch, Boolean(src && src !== "original" && ids.has(src)));
    }
    const inputIsMask = branchIsMask.get(branch) ?? false;
    const outputIsMask = node.type === "make_mask" ? true : inputIsMask;
    branchIsMask.set(branch, outputIsMask);
    if (outputIsMask) ids.add(node.id);
  }
  return ids;
}

function maskProviderLabel(node: PipelineNode): string {
  return `${node.branch}: ${node.type} (${node.id.slice(0, 6)})`;
}

/** Only outputs flowing through a mask branch may be reused as masks. */
export function maskSourceOptionsForConsumer(
  nodes: PipelineNode[],
  consumerId: string,
  branchSources: BranchSources = {}
) {
  const consumer = nodes.find((n) => n.id === consumerId);
  if (
    !consumer ||
    (consumer.type !== "blur" && consumer.type !== "noise" && consumer.type !== "hf_image_to_image")
  ) {
    return [];
  }
  const providers = maskCapableNodeIds(nodes, branchSources);

  return nodes
    .filter((node) => node.id !== consumerId && providers.has(node.id))
    .map((node) => ({ id: node.id, label: maskProviderLabel(node) }));
}

export function resolveNodeId(node: PipelineNode, index: number): string {
  return node.id?.trim() ? node.id : `node-${index}`;
}

/** First occurrence of `branch` in the flat pipeline list (matches lane order in the UI). */
export function firstFlatIndexForBranch(nodes: PipelineNode[], branch: string): number {
  const b = normalizedBranch(branch);
  for (let i = 0; i < nodes.length; i++) {
    if (normalizedBranch(nodes[i].branch) === b) return i;
  }
  return -1;
}

function branchesInPipeline(nodes: PipelineNode[]): string[] {
  const s = new Set<string>(["main"]);
  for (const n of nodes) s.add(normalizedBranch(n.branch));
  return [...s];
}

/**
 * Same topological order as backend: mask edges (provider → consumer), plus branch-entry edges
 * (fork source node → first node on that branch in flat order) so a branch can start from any
 * prior-computed node on another lane, not only those listed before the branch in mask-only order.
 */
export function orderPipelineNodes(
  pipelineNodes: PipelineNode[],
  branchSources: BranchSources = {},
  validateMaskProviders = true
): PipelineNode[] {
  const n = pipelineNodes.length;
  if (n === 0) return [];

  const nodeIds = pipelineNodes.map((node, i) => resolveNodeId(node, i));
  const seen = new Set<string>();
  for (const nid of nodeIds) {
    if (seen.has(nid)) throw new Error(`Duplicate pipeline node id: ${nid}`);
    seen.add(nid);
  }

  const idToIndex: Record<string, number> = {};
  for (let i = 0; i < n; i++) idToIndex[nodeIds[i]] = i;

  const indegree = new Array(n).fill(0);
  const adj: number[][] = Array.from({ length: n }, () => []);
  const edgeSeen = new Set<string>();
  const addEdge = (providerIndex: number, consumerIndex: number) => {
    if (providerIndex === consumerIndex) return;
    const key = `${providerIndex}->${consumerIndex}`;
    if (edgeSeen.has(key)) return;
    edgeSeen.add(key);
    adj[providerIndex].push(consumerIndex);
    indegree[consumerIndex]++;
  };

  for (let consumerIndex = 0; consumerIndex < n; consumerIndex++) {
    const params = pipelineNodes[consumerIndex].params;
    const maskRef = "maskNodeId" in params ? params.maskNodeId : undefined;
    if (!maskRef) continue;
    const maskKey = String(maskRef);
    if (!(maskKey in idToIndex)) {
      throw new Error(
        `Mask node id not found in pipeline: ${maskKey}. Add the mask node or fix the reference.`
      );
    }
    const providerIndex = idToIndex[maskKey];
    if (providerIndex === consumerIndex) {
      throw new Error(`Node cannot reference itself as mask: ${maskKey}`);
    }
    addEdge(providerIndex, consumerIndex);
  }

  for (const branch of branchesInPipeline(pipelineNodes)) {
    if (branch === "main") continue;
    const raw = branchSources[branch];
    const entry =
      raw === undefined || raw === null || String(raw).trim() === ""
        ? "original"
        : String(raw).trim();
    if (entry.toLowerCase() === "original") continue;
    if (!(entry in idToIndex)) continue;
    const firstIdx = firstFlatIndexForBranch(pipelineNodes, branch);
    if (firstIdx < 0) continue;
    const providerIndex = idToIndex[entry];
    addEdge(providerIndex, firstIdx);
  }

  const indegreeRemaining = [...indegree];
  const orderIndices: number[] = [];
  const processed = new Set<number>();

  for (let _ = 0; _ < n; _++) {
    const ready: number[] = [];
    for (let i = 0; i < n; i++) {
      if (indegreeRemaining[i] === 0 && !processed.has(i)) ready.push(i);
    }
    if (ready.length === 0) {
      throw new Error("Cycle in pipeline dependencies (mask links and/or branch entry sources).");
    }
    const pick = Math.min(...ready);
    orderIndices.push(pick);
    processed.add(pick);
    for (const successor of adj[pick]) indegreeRemaining[successor]--;
  }

  const ordered = orderIndices.map((i) => pipelineNodes[i]);
  if (!validateMaskProviders) return ordered;

  const maskCapable = maskCapableNodeIds(ordered, branchSources);
  for (const node of ordered) {
    const maskRef = "maskNodeId" in node.params ? node.params.maskNodeId : undefined;
    if (maskRef && !maskCapable.has(String(maskRef))) {
      throw new Error(
        `Node ${node.id} references a non-mask output (${String(maskRef)}). Start from make_mask or from a branch forked from a mask output.`
      );
    }
  }
  return ordered;
}

/** @deprecated Prefer firstFlatIndexForBranch for fork semantics; kept for callers that need order position. */
export function firstBranchNodeIndexInOrder(ordered: PipelineNode[], branch: string): number {
  const b = normalizedBranch(branch);
  for (let i = 0; i < ordered.length; i++) {
    const nb = normalizedBranch(ordered[i].branch);
    if (nb === b) return i;
  }
  return -1;
}

/**
 * Fork entry for a side branch: original image, or any node not on that branch (outputs on other
 * lanes / main). Execution order is computed with mask deps + fork deps via `orderPipelineNodes`.
 */
export function branchEntrySourceOptions(
  nodes: PipelineNode[],
  branch: string
): { value: string; label: string }[] {
  const opts: { value: string; label: string }[] = [{ value: "original", label: "Original image" }];
  if (normalizedBranch(branch) === "main") return opts;

  const br = normalizedBranch(branch);
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    if (normalizedBranch(node.branch) === br) continue;
    opts.push({
      value: resolveNodeId(node, i),
      label: `${node.branch}: ${node.type} (${node.id.slice(0, 8)})`
    });
  }
  return opts;
}

export function resolveBranchSourcesForSubmit(
  nodes: PipelineNode[],
  knownBranches: string[],
  branchSources: BranchSources
): BranchSources {
  const out: BranchSources = {};
  for (const b of knownBranches) {
    if (b === "main") continue;
    const allowed = new Set(branchEntrySourceOptions(nodes, b).map((o) => o.value));
    const want = branchSources[b] ?? "original";
    out[b] = allowed.has(want) ? want : "original";
  }
  try {
    orderPipelineNodes(nodes, out);
  } catch {
    const fallback: BranchSources = {};
    for (const b of knownBranches) {
      if (b === "main") continue;
      fallback[b] = "original";
    }
    return fallback;
  }
  return out;
}

export function knownBranchesFromNodes(nodes: PipelineNode[]): string[] {
  const set = new Set<string>(["main"]);
  for (const node of nodes) set.add(node.branch);
  return [...set];
}

export function nodesByBranchGroups(nodes: PipelineNode[]) {
  const branches = knownBranchesFromNodes(nodes);
  return branches.map((branch) => ({ branch, nodes: nodes.filter((node) => node.branch === branch) }));
}

export function buildProcessFormData(
  file: File,
  nodes: PipelineNode[],
  previewNodeId: string,
  branchSources: BranchSources,
  knownBranches: string[],
  skipNodeTypes: string[] = [],
  cachedNodeOutputBlobs: Map<string, Blob> = new Map()
): FormData {
  const resolved = resolveBranchSourcesForSubmit(nodes, knownBranches, branchSources);
  const payload = {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      branch: node.branch,
      params: node.params
    })),
    branchSources: resolved
  };

  const formData = new FormData();
  formData.append("image", file);
  formData.append("pipeline", JSON.stringify(payload));
  if (previewNodeId !== "final") {
    formData.append("preview_node_id", previewNodeId);
  }
  if (skipNodeTypes.length > 0) {
    formData.append("skip_node_types", JSON.stringify(skipNodeTypes));
  }
  for (const [nodeId, blob] of cachedNodeOutputBlobs) {
    formData.append(`cached_output:${nodeId}`, blob, `${nodeId}.png`);
  }
  return formData;
}

export async function fetchProcessedImageBlob(
  apiUrl: string,
  file: File,
  nodes: PipelineNode[],
  previewNodeId: string,
  branchSources: BranchSources,
  knownBranches: string[],
  skipNodeTypes: string[] = [],
  cachedNodeOutputBlobs: Map<string, Blob> = new Map()
): Promise<Blob> {
  const formData = buildProcessFormData(
    file,
    nodes,
    previewNodeId,
    branchSources,
    knownBranches,
    skipNodeTypes,
    cachedNodeOutputBlobs
  );
  const response = await fetch(apiUrl, { method: "POST", body: formData, credentials: "include" });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to process image");
  }
  return response.blob();
}

export function moveNodeBranchUp(n: PipelineNode, knownBranches: string[]): PipelineNode {
  const from = knownBranches.indexOf(n.branch);
  if (from <= 0) return n;
  return { ...n, branch: knownBranches[from - 1] };
}

export function moveNodeBranchDown(n: PipelineNode, knownBranches: string[]): PipelineNode {
  const from = knownBranches.indexOf(n.branch);
  if (from < knownBranches.length - 1) {
    return { ...n, branch: knownBranches[from + 1] };
  }
  const newBranch = `branch-${knownBranches.length}`;
  return { ...n, branch: newBranch };
}

export function withBlurRadius(n: PipelineNode, radius: number): PipelineNode {
  return n.type === "blur" ? { ...n, params: { ...n.params, radius } } : n;
}

export function withBlurMask(n: PipelineNode, maskNodeId: string | undefined): PipelineNode {
  return n.type === "blur" ? { ...n, params: { ...n.params, maskNodeId } } : n;
}

export function withNoiseIntensity(n: PipelineNode, intensity: number): PipelineNode {
  return n.type === "noise" ? { ...n, params: { ...n.params, intensity } } : n;
}

export function withNoiseSeed(n: PipelineNode, seed: number): PipelineNode {
  return n.type === "noise" ? { ...n, params: { ...n.params, seed } } : n;
}

export function withNoiseMask(n: PipelineNode, maskNodeId: string | undefined): PipelineNode {
  return n.type === "noise" ? { ...n, params: { ...n.params, maskNodeId } } : n;
}

export function withMakeMaskThreshold(n: PipelineNode, threshold: number): PipelineNode {
  return n.type === "make_mask" ? { ...n, params: { ...n.params, threshold } } : n;
}

export function withMakeMaskInvert(n: PipelineNode, invert: boolean): PipelineNode {
  return n.type === "make_mask" ? { ...n, params: { ...n.params, invert } } : n;
}

export function withHfModel(n: PipelineNode, model: string): PipelineNode {
  return n.type === "hf_image_to_image" ? { ...n, params: { ...n.params, model } } : n;
}

export function withHfPrompt(n: PipelineNode, prompt: string): PipelineNode {
  return n.type === "hf_image_to_image" ? { ...n, params: { ...n.params, prompt } } : n;
}

export function withHfProvider(n: PipelineNode, provider: string): PipelineNode {
  return n.type === "hf_image_to_image" ? { ...n, params: { ...n.params, provider } } : n;
}

export function withHfMask(n: PipelineNode, maskNodeId: string | undefined): PipelineNode {
  return n.type === "hf_image_to_image" ? { ...n, params: { ...n.params, maskNodeId } } : n;
}

export function withHfDebug(n: PipelineNode, debug: boolean): PipelineNode {
  return n.type === "hf_image_to_image" ? { ...n, params: { ...n.params, debug } } : n;
}

export function hfNodeIsDebug(node: PipelineNode): boolean {
  return node.type === "hf_image_to_image" && node.params.debug === true;
}

export function pipelineHasHfNode(nodes: PipelineNode[]): boolean {
  return nodes.some((n) => n.type === "hf_image_to_image");
}

/** Auto-preview skips HF inference so local nodes update quickly. Manual runs pass skipHf: false. */
export function shouldSkipHfNodes(nodes: PipelineNode[]): boolean {
  return pipelineHasHfNode(nodes);
}

export function hfCacheSignature(
  hfNodeId: string,
  nodes: PipelineNode[],
  branchSources: BranchSources,
  knownBranches: string[]
): string | null {
  const hfNode = nodes.find((n) => n.id === hfNodeId);
  if (!hfNode || hfNode.type !== "hf_image_to_image") return null;

  const resolved = resolveBranchSourcesForSubmit(nodes, knownBranches, branchSources);

  let ordered: PipelineNode[];
  try {
    ordered = orderPipelineNodes(nodes, resolved);
  } catch {
    return null;
  }

  const hfIndex = ordered.findIndex((n) => n.id === hfNodeId);
  if (hfIndex < 0) return null;

  const branch = hfNode.branch;
  const branchEntry = branch === "main" ? "original" : (resolved[branch] ?? "original");
  const upstream = ordered.slice(0, hfIndex).map((n) => ({
    id: n.id,
    type: n.type,
    branch: n.branch,
    params: n.params
  }));

  return JSON.stringify({ upstream, branchEntry, hfParams: hfNode.params });
}

export type HfOutputCacheEntry = { url: string; signature: string; blob: Blob };

export function getCachedNodeOutputBlobs(
  cache: Map<string, HfOutputCacheEntry>
): Map<string, Blob> {
  const blobs = new Map<string, Blob>();
  for (const [nodeId, entry] of cache) {
    blobs.set(nodeId, entry.blob);
  }
  return blobs;
}
