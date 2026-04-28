import { useEffect, useMemo, useRef, useState } from "react";
import {
  applyNodeUpdate,
  branchEntrySourceOptions,
  createNode,
  DEFAULT_PROCESS_API_URL,
  fetchProcessedImageBlob,
  knownBranchesFromNodes,
  maskSourceOptionsForConsumer,
  moveNodeBranchDown,
  moveNodeBranchUp,
  nodesByBranchGroups,
  canReorderNodeInBranch,
  orderPipelineNodes,
  removeNodeFromList,
  reorderNodesWithinBranch,
  withBlurMask,
  withBlurRadius,
  withMakeMaskInvert,
  withMakeMaskThreshold,
  withNoiseIntensity,
  withNoiseMask,
  withNoiseSeed
} from "./pipelineLogic";
import type { BranchSources, NodeType, PipelineNode } from "./pipelineTypes";

export default function App() {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [processedUrl, setProcessedUrl] = useState<string | null>(null);
  const [nodes, setNodes] = useState<PipelineNode[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNodePicker, setShowNodePicker] = useState(false);
  const [previewNodeId, setPreviewNodeId] = useState<string>("final");
  const [branchSources, setBranchSources] = useState<BranchSources>({});
  const timerRef = useRef<number | null>(null);

  const canDownload = useMemo(() => Boolean(processedUrl), [processedUrl]);

  useEffect(() => {
    return () => {
      if (originalUrl) URL.revokeObjectURL(originalUrl);
      if (processedUrl) URL.revokeObjectURL(processedUrl);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [originalUrl, processedUrl]);

  const onUpload = (file: File | null) => {
    if (!file) return;
    if (originalUrl) URL.revokeObjectURL(originalUrl);
    if (processedUrl) URL.revokeObjectURL(processedUrl);
    const fileUrl = URL.createObjectURL(file);
    setUploadedFile(file);
    setOriginalUrl(fileUrl);
    setProcessedUrl(null);
    setError(null);
  };

  const updateNode = (id: string, updater: (node: PipelineNode) => PipelineNode) => {
    setNodes((prev) => applyNodeUpdate(prev, id, updater));
  };

  const removeNode = (id: string) => {
    setNodes((prev) => removeNodeFromList(prev, id));
  };

  const moveNode = (index: number, direction: -1 | 1) => {
    setNodes((prev) => reorderNodesWithinBranch(prev, index, direction));
  };

  const addNode = (type: NodeType) => {
    setNodes((prev) => [...prev, createNode(type)]);
    setShowNodePicker(false);
  };

  const maskPickerByNodeId = useMemo(() => {
    const map = new Map<string, { id: string; label: string }[]>();
    for (const n of nodes) {
      if (n.type === "blur" || n.type === "noise") {
        map.set(n.id, maskSourceOptionsForConsumer(nodes, n.id, branchSources));
      }
    }
    return map;
  }, [nodes, branchSources]);

  const knownBranches = useMemo(() => knownBranchesFromNodes(nodes), [nodes]);

  useEffect(() => {
    setBranchSources((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const b of knownBranches) {
        if (b === "main") continue;
        if (next[b] === undefined) {
          next[b] = "original";
          changed = true;
        }
      }
      try {
        for (const b of knownBranches) {
          if (b === "main") continue;
          const allowed = new Set(branchEntrySourceOptions(nodes, b).map((o) => o.value));
          const raw = next[b] ?? "original";
          if (!allowed.has(raw)) {
            next[b] = "original";
            changed = true;
          }
        }
        orderPipelineNodes(nodes, next);
      } catch {
        for (const b of knownBranches) {
          if (b === "main") continue;
          if (next[b] !== "original") {
            next[b] = "original";
            changed = true;
          }
        }
      }
      for (const key of Object.keys(next)) {
        if (key !== "main" && !knownBranches.includes(key)) {
          delete next[key];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [nodes, knownBranches, branchSources]);

  const nodesByBranch = useMemo(() => nodesByBranchGroups(nodes), [nodes]);

  const processImage = async () => {
    if (!uploadedFile) return;

    setIsProcessing(true);
    setError(null);

    try {
      const blob = await fetchProcessedImageBlob(
        DEFAULT_PROCESS_API_URL,
        uploadedFile,
        nodes,
        previewNodeId,
        branchSources,
        knownBranches
      );
      const url = URL.createObjectURL(blob);
      if (processedUrl) URL.revokeObjectURL(processedUrl);
      setProcessedUrl(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsProcessing(false);
    }
  };

  useEffect(() => {
    if (!uploadedFile) return;
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      void processImage();
    }, 180);
  }, [nodes, uploadedFile, previewNodeId, branchSources, knownBranches]);

  useEffect(() => {
    if (previewNodeId === "final") return;
    const stillExists = nodes.some((node) => node.id === previewNodeId);
    if (!stillExists) setPreviewNodeId("final");
  }, [nodes, previewNodeId]);

  return (
    <div className="app">
      <header className="topbar">
        <label className="button">
          Upload
          <input
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => onUpload(e.target.files?.[0] ?? null)}
          />
        </label>

        <button className="button" onClick={() => void processImage()} disabled={!uploadedFile || isProcessing}>
          {isProcessing ? "Processing..." : "Process"}
        </button>

        <a
          className={`button ${!canDownload ? "button-disabled" : ""}`}
          href={processedUrl ?? "#"}
          download="processed.png"
          onClick={(e) => {
            if (!canDownload) e.preventDefault();
          }}
        >
          Download
        </a>
      </header>

      <main className="viewport">
        <section className="panel">
          <h3>Original</h3>
          {originalUrl ? <img src={originalUrl} alt="Original" /> : <div className="placeholder">Upload an image</div>}
        </section>
        <section className="panel">
          <div className="panel-head">
            <h3>Processed</h3>
            <button className="button mini-preview" onClick={() => setPreviewNodeId("final")}>
              Show Final
            </button>
          </div>
          {processedUrl ? (
            <img src={processedUrl} alt="Processed" />
          ) : (
            <div className="placeholder">Add nodes and process</div>
          )}
        </section>
      </main>

      <footer className="nodes">
        <div className="nodes-toolbar">
          <div className="node-picker">
            <button className="button plus-button" onClick={() => setShowNodePicker((v) => !v)}>
              + Node
            </button>
            {showNodePicker && (
              <div className="node-picker-menu">
                <button className="menu-item" onClick={() => addNode("blur")}>
                  Blur
                </button>
                <button className="menu-item" onClick={() => addNode("noise")}>
                  Noise
                </button>
                <button className="menu-item" onClick={() => addNode("make_mask")}>
                  Make Mask
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="branch-list">
          {nodes.length === 0 && <div className="placeholder">No nodes. Add blur or noise.</div>}
          {nodesByBranch.map((branchGroup) => (
            <section className="branch-lane" key={branchGroup.branch}>
              <div className="branch-title">{branchGroup.branch}</div>
              {branchGroup.branch !== "main" && (
                <label className="field branch-entry">
                  <span className="branch-entry-label">Entry from</span>
                  <span className="branch-entry-hint">
                    Entry from another lane or main (not from this branch). Execution order follows mask links and
                    these fork links; ← → only swaps within the same branch.
                  </span>
                  <select
                    value={branchSources[branchGroup.branch] ?? "original"}
                    onChange={(e) =>
                      setBranchSources((prev) => ({
                        ...prev,
                        [branchGroup.branch]: e.target.value
                      }))
                    }
                  >
                    {branchEntrySourceOptions(nodes, branchGroup.branch).map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="node-list">
                {branchGroup.nodes.map((node) => {
                  const index = nodes.findIndex((n) => n.id === node.id);
                  const branchIndex = knownBranches.indexOf(node.branch);
                  return (
                    <div className="node-card" key={node.id}>
                      <div className="node-head">
                        <strong>{node.type.toUpperCase()}</strong>
                        <div className="node-actions">
                          <button
                            className="mini"
                            onClick={() => updateNode(node.id, (n) => moveNodeBranchUp(n, knownBranches))}
                            disabled={branchIndex <= 0}
                            title="Move to upper branch"
                          >
                            ↑
                          </button>
                          <button
                            className="mini"
                            onClick={() => updateNode(node.id, (n) => moveNodeBranchDown(n, knownBranches))}
                            title="Move to lower branch"
                          >
                            ↓
                          </button>
                          <button
                            className="mini"
                            onClick={() => moveNode(index, -1)}
                            disabled={!canReorderNodeInBranch(nodes, index, -1)}
                            title="Swap with the previous node on this branch (skips other lanes in the flat list)"
                          >
                            ←
                          </button>
                          <button
                            className="mini"
                            onClick={() => moveNode(index, 1)}
                            disabled={!canReorderNodeInBranch(nodes, index, 1)}
                            title="Swap with the next node on this branch (skips other lanes in the flat list)"
                          >
                            →
                          </button>
                          <button
                            className={`mini ${previewNodeId === node.id ? "active-branch" : ""}`}
                            onClick={() => setPreviewNodeId(node.id)}
                            title="Show this node in viewport"
                          >
                            V
                          </button>
                          <button className="mini danger" onClick={() => removeNode(node.id)}>
                            x
                          </button>
                        </div>
                      </div>

                      {node.type === "blur" && (
                        <label className="field">
                          Radius: {node.params.radius.toFixed(1)}
                          <input
                            type="range"
                            min={0}
                            max={30}
                            step={0.5}
                            value={node.params.radius}
                            onChange={(e) =>
                              updateNode(node.id, (n) => withBlurRadius(n, Number(e.target.value)))
                            }
                          />
                          <select
                            value={node.params.maskNodeId ?? ""}
                            onChange={(e) =>
                              updateNode(node.id, (n) =>
                                withBlurMask(n, e.target.value || undefined)
                              )
                            }
                          >
                            <option value="">No mask</option>
                            {(maskPickerByNodeId.get(node.id) ?? []).map((maskNode) => (
                              <option key={maskNode.id} value={maskNode.id}>
                                {maskNode.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}

                      {node.type === "noise" && (
                        <>
                          <label className="field">
                            Intensity: {node.params.intensity.toFixed(0)}
                            <input
                              type="range"
                              min={0}
                              max={100}
                              step={1}
                              value={node.params.intensity}
                              onChange={(e) =>
                                updateNode(node.id, (n) =>
                                  withNoiseIntensity(n, Number(e.target.value))
                                )
                              }
                            />
                          </label>
                          <label className="field inline-field">
                            Seed:
                            <input
                              type="number"
                              min={0}
                              step={1}
                              value={node.params.seed ?? 0}
                              onChange={(e) =>
                                updateNode(node.id, (n) =>
                                  withNoiseSeed(n, Number(e.target.value) || 0)
                                )
                              }
                            />
                          </label>
                          <label className="field">
                            <select
                              value={node.params.maskNodeId ?? ""}
                              onChange={(e) =>
                                updateNode(node.id, (n) =>
                                  withNoiseMask(n, e.target.value || undefined)
                                )
                              }
                            >
                              <option value="">No mask</option>
                              {(maskPickerByNodeId.get(node.id) ?? []).map((maskNode) => (
                                <option key={maskNode.id} value={maskNode.id}>
                                  {maskNode.label}
                                </option>
                              ))}
                            </select>
                          </label>
                        </>
                      )}

                      {node.type === "make_mask" && (
                        <>
                          <label className="field">
                            Threshold: {node.params.threshold}
                            <input
                              type="range"
                              min={0}
                              max={255}
                              step={1}
                              value={node.params.threshold}
                              onChange={(e) =>
                                updateNode(node.id, (n) =>
                                  withMakeMaskThreshold(n, Number(e.target.value))
                                )
                              }
                            />
                          </label>
                          <label className="field inline-field">
                            <input
                              type="checkbox"
                              checked={node.params.invert}
                              onChange={(e) =>
                                updateNode(node.id, (n) => withMakeMaskInvert(n, e.target.checked))
                              }
                            />
                            Invert
                          </label>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        {error && <div className="error">Error: {error}</div>}
      </footer>
    </div>
  );
}
