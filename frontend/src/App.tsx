import { useEffect, useMemo, useRef, useState } from "react";

type NodeType = "blur" | "noise" | "make_mask";

type BlurNode = {
  id: string;
  type: "blur";
  branch: string;
  params: { radius: number; maskNodeId?: string };
};

type NoiseNode = {
  id: string;
  type: "noise";
  branch: string;
  params: { intensity: number; maskNodeId?: string };
};

type MakeMaskNode = {
  id: string;
  type: "make_mask";
  branch: string;
  params: { threshold: number; invert: boolean };
};

type PipelineNode = BlurNode | NoiseNode | MakeMaskNode;

const API_URL = "http://localhost:8000/process-image";

function createNode(type: NodeType): PipelineNode {
  const id = `${type}-${crypto.randomUUID()}`;
  if (type === "blur") {
    return { id, type, branch: "main", params: { radius: 4 } };
  }
  if (type === "noise") {
    return { id, type, branch: "main", params: { intensity: 20 } };
  }
  return { id, type, branch: "main", params: { threshold: 128, invert: false } };
}

export default function App() {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [processedUrl, setProcessedUrl] = useState<string | null>(null);
  const [nodes, setNodes] = useState<PipelineNode[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNodePicker, setShowNodePicker] = useState(false);
  const [previewNodeId, setPreviewNodeId] = useState<string>("final");
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
    setNodes((prev) => {
      const previousMaskByNodeId = new Map(
        prev
          .filter((n): n is BlurNode | NoiseNode => n.type === "blur" || n.type === "noise")
          .map((n) => [n.id, n.params.maskNodeId])
      );

      const next = prev.map((n) => (n.id === id ? updater(n) : n));

      return next.map((n) => {
        if (n.type !== "blur" && n.type !== "noise") return n;
        const prevMask = previousMaskByNodeId.get(n.id);
        if (!prevMask || n.params.maskNodeId) return n;
        return {
          ...n,
          params: {
            ...n.params,
            maskNodeId: prevMask
          }
        };
      });
    });
  };

  const removeNode = (id: string) => {
    setNodes((prev) => prev.filter((n) => n.id !== id));
  };

  const moveNode = (index: number, direction: -1 | 1) => {
    setNodes((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const addNode = (type: NodeType) => {
    setNodes((prev) => [...prev, createNode(type)]);
    setShowNodePicker(false);
  };

  const maskNodeOptions = useMemo(
    () =>
      nodes.map((node) => ({
        id: node.id,
        label: `${node.branch}: ${node.type} (${node.id.slice(0, 6)})`
      })),
    [nodes]
  );

  const knownBranches = useMemo(() => {
    const set = new Set<string>(["main"]);
    for (const node of nodes) set.add(node.branch);
    return [...set];
  }, [nodes]);

  const nodesByBranch = useMemo(
    () => knownBranches.map((branch) => ({ branch, nodes: nodes.filter((node) => node.branch === branch) })),
    [knownBranches, nodes]
  );

  const processImage = async () => {
    if (!uploadedFile) return;

    const payload = {
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        branch: node.branch,
        params: node.params
      }))
    };

    const formData = new FormData();
    formData.append("image", uploadedFile);
    formData.append("pipeline", JSON.stringify(payload));
    if (previewNodeId !== "final") {
      formData.append("preview_node_id", previewNodeId);
    }

    setIsProcessing(true);
    setError(null);

    try {
      const response = await fetch(API_URL, { method: "POST", body: formData });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to process image");
      }

      const blob = await response.blob();
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
  }, [nodes, uploadedFile, previewNodeId]);

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
                    onClick={() =>
                      updateNode(node.id, (n) => {
                        const from = knownBranches.indexOf(n.branch);
                        if (from <= 0) return n;
                        return { ...n, branch: knownBranches[from - 1] };
                      })
                    }
                    disabled={branchIndex <= 0}
                    title="Move to upper branch"
                  >
                    ↑
                  </button>
                  <button
                    className="mini"
                    onClick={() =>
                      updateNode(node.id, (n) => {
                        const from = knownBranches.indexOf(n.branch);
                        if (from < knownBranches.length - 1) {
                          return { ...n, branch: knownBranches[from + 1] };
                        }
                        const newBranch = `branch-${knownBranches.length}`;
                        return { ...n, branch: newBranch };
                      })
                    }
                    title="Move to lower branch"
                  >
                    ↓
                  </button>
                  <button className="mini" onClick={() => moveNode(index, -1)} disabled={index === 0}>
                    ←
                  </button>
                  <button
                    className="mini"
                    onClick={() => moveNode(index, 1)}
                    disabled={index === nodes.length - 1}
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
                      updateNode(node.id, (n) =>
                        n.type === "blur"
                          ? {
                              ...n,
                              params: {
                                ...n.params,
                                radius: Number(e.target.value)
                              }
                            }
                          : n
                      )
                    }
                  />
                  <select
                    value={node.params.maskNodeId ?? ""}
                    onChange={(e) =>
                      updateNode(node.id, (n) =>
                        n.type === "blur"
                          ? {
                              ...n,
                              params: {
                                ...n.params,
                                maskNodeId: e.target.value || undefined
                              }
                            }
                          : n
                      )
                    }
                  >
                    <option value="">No mask</option>
                    {maskNodeOptions.map((maskNode) => (
                      <option key={maskNode.id} value={maskNode.id}>
                        {maskNode.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {node.type === "noise" && (
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
                        n.type === "noise"
                          ? {
                              ...n,
                              params: {
                                ...n.params,
                                intensity: Number(e.target.value)
                              }
                            }
                          : n
                      )
                    }
                  />
                  <select
                    value={node.params.maskNodeId ?? ""}
                    onChange={(e) =>
                      updateNode(node.id, (n) =>
                        n.type === "noise"
                          ? {
                              ...n,
                              params: {
                                ...n.params,
                                maskNodeId: e.target.value || undefined
                              }
                            }
                          : n
                      )
                    }
                  >
                    <option value="">No mask</option>
                    {maskNodeOptions.map((maskNode) => (
                      <option key={maskNode.id} value={maskNode.id}>
                        {maskNode.label}
                      </option>
                    ))}
                  </select>
                </label>
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
                          n.type === "make_mask"
                            ? { ...n, params: { ...n.params, threshold: Number(e.target.value) } }
                            : n
                        )
                      }
                    />
                  </label>
                  <label className="field inline-field">
                    <input
                      type="checkbox"
                      checked={node.params.invert}
                      onChange={(e) =>
                        updateNode(node.id, (n) =>
                          n.type === "make_mask"
                            ? { ...n, params: { ...n.params, invert: e.target.checked } }
                            : n
                        )
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
