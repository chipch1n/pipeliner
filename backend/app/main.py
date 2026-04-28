import io
import json
from typing import Any, Dict, FrozenSet, List, Tuple

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image
from PIL.Image import DecompressionBombError

from .nodes import create_node

# Decompression bomb and memory exhaustion mitigations for uploaded images.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB raw body per part (compressed on wire)
# Declared multipart part types we accept before sniffing PIL format from headers only.
_ALLOWED_PART_CONTENT_TYPES: FrozenSet[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "application/octet-stream"}
)
_CONTENT_TYPE_TO_PIL: Dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}
# Reject naive huge POST before buffering when Content-Length is known (multipart adds overhead).
_MAX_REQUEST_BODY_BYTES = _MAX_UPLOAD_BYTES + 1024 * 512
_ALLOWED_PIL_FORMATS: FrozenSet[str] = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
# Hard cap on decoded pixel count (Pillow default is very high; keep explicit).
Image.MAX_IMAGE_PIXELS = 32_000_000  # ~32 MP

app = FastAPI(title="Pipeliner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_body_hint(request: Request, call_next):
    """Reject oversized bodies early when Content-Length is present (cheap DoS mitigation)."""
    if request.method in ("POST", "PUT", "PATCH"):
        raw_cl = request.headers.get("content-length")
        if raw_cl is not None:
            try:
                content_length = int(raw_cl)
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length header"},
                    status_code=400,
                )
            if content_length > _MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    {
                        "detail": (
                            f"Request body exceeds maximum ({_MAX_REQUEST_BODY_BYTES // (1024 * 1024)} MiB)."
                        )
                    },
                    status_code=413,
                )
    return await call_next(request)


def _normalized_part_content_type(upload: UploadFile) -> str:
    ct = upload.content_type
    if not ct:
        return ""
    return ct.split(";")[0].strip().lower()


def _open_validated_upload(raw: bytes, upload: UploadFile) -> Image.Image:
    """Validate declared type, Pillow format sniff (headers), then decode once (MAX_IMAGE_PIXELS)."""
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    ct = _normalized_part_content_type(upload)
    if ct and ct not in _ALLOWED_PART_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported Content-Type for image part: {ct}",
        )

    try:
        input_image = Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    pil_fmt = input_image.format
    if not pil_fmt or pil_fmt not in _ALLOWED_PIL_FORMATS:
        try:
            input_image.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail="Unsupported or unrecognized image format (allowed: JPEG, PNG, WEBP, GIF).",
        )

    if ct.startswith("image/"):
        expected = _CONTENT_TYPE_TO_PIL.get(ct)
        if expected and pil_fmt != expected:
            try:
                input_image.close()
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="Content-Type does not match image data.")

    try:
        input_image.load()
    except DecompressionBombError as exc:
        try:
            input_image.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail="Image dimensions or pixel count exceed server limits (decompression bomb protection).",
        ) from exc
    except Exception as exc:
        try:
            input_image.close()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    return input_image


def _resolve_node_id(node: Dict[str, Any], index: int) -> str:
    return str(node.get("id") or f"node-{index}")


def _first_flat_index_for_branch(pipeline_nodes: List[Dict[str, Any]], branch: str) -> int:
    b = str(branch).strip() or "main"
    for i, node in enumerate(pipeline_nodes):
        nb = str(node.get("branch", "main")).strip() or "main"
        if nb == b:
            return i
    return -1


def _branches_in_pipeline(pipeline_nodes: List[Dict[str, Any]]) -> set[str]:
    out: set[str] = {"main"}
    for node in pipeline_nodes:
        out.add(str(node.get("branch", "main")).strip() or "main")
    return out


def _mask_capable_node_ids(
    ordered_nodes: List[Dict[str, Any]],
    branch_sources: Dict[str, str] | None = None,
) -> set[str]:
    ids: set[str] = set()
    branch_is_mask: Dict[str, bool] = {"main": False}
    src_map = branch_sources or {}
    for index, node in enumerate(ordered_nodes):
        branch = str(node.get("branch", "main")).strip() or "main"
        if branch not in branch_is_mask:
            src = str(src_map.get(branch, "original")).strip()
            branch_is_mask[branch] = src != "original" and src in ids
        input_is_mask = branch_is_mask.get(branch, False)
        output_is_mask = str(node.get("type") or "") == "make_mask" or input_is_mask
        branch_is_mask[branch] = output_is_mask
        if output_is_mask:
            ids.add(_resolve_node_id(node, index))
    return ids


def order_pipeline_nodes(
    pipeline_nodes: List[Dict[str, Any]],
    branch_sources: Dict[str, str] | None = None,
    validate_mask_providers: bool = True,
) -> List[Dict[str, Any]]:
    """Topological order: mask edges (provider → consumer) plus branch fork (entry node → first node on branch)."""
    n = len(pipeline_nodes)
    if n == 0:
        return []

    node_ids = [_resolve_node_id(pipeline_nodes[i], i) for i in range(n)]
    seen: set[str] = set()
    for nid in node_ids:
        if nid in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate pipeline node id: {nid}")
        seen.add(nid)

    id_to_index = {node_ids[i]: i for i in range(n)}

    indegree = [0] * n
    adj: List[List[int]] = [[] for _ in range(n)]
    edge_seen: set[tuple[int, int]] = set()

    def add_edge(provider_index: int, consumer_index: int) -> None:
        if provider_index == consumer_index:
            return
        key = (provider_index, consumer_index)
        if key in edge_seen:
            return
        edge_seen.add(key)
        adj[provider_index].append(consumer_index)
        indegree[consumer_index] += 1

    for consumer_index, node in enumerate(pipeline_nodes):
        params = node.get("params") or {}
        mask_ref = params.get("maskNodeId")
        if not mask_ref:
            continue
        mask_key = str(mask_ref)
        if mask_key not in id_to_index:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Mask node id not found in pipeline: {mask_key}. "
                    "Add the mask node to the pipeline or fix the reference."
                ),
            )
        provider_index = id_to_index[mask_key]
        if provider_index == consumer_index:
            raise HTTPException(
                status_code=400,
                detail=f"Node cannot reference itself as mask: {mask_key}",
            )
        add_edge(provider_index, consumer_index)

    src_map = branch_sources or {}
    for branch in _branches_in_pipeline(pipeline_nodes):
        if branch == "main":
            continue
        raw = src_map.get(branch)
        if raw is None or str(raw).strip() == "":
            entry = "original"
        else:
            entry = str(raw).strip()
        if entry.lower() == "original":
            continue
        if entry not in id_to_index:
            continue
        first_idx = _first_flat_index_for_branch(pipeline_nodes, branch)
        if first_idx < 0:
            continue
        provider_index = id_to_index[entry]
        add_edge(provider_index, first_idx)

    indegree_remaining = list(indegree)
    order_indices: List[int] = []
    processed: set[int] = set()

    for _ in range(n):
        ready = [i for i in range(n) if indegree_remaining[i] == 0 and i not in processed]
        if not ready:
            raise HTTPException(
                status_code=400,
                detail="Cycle in pipeline dependencies (mask links and/or branch entry sources).",
            )
        pick = min(ready)
        order_indices.append(pick)
        processed.add(pick)
        for successor in adj[pick]:
            indegree_remaining[successor] -= 1

    ordered = [pipeline_nodes[i] for i in order_indices]
    if not validate_mask_providers:
        return ordered

    mask_capable = _mask_capable_node_ids(ordered, branch_sources)
    for consumer_index, node in enumerate(ordered):
        params = node.get("params") or {}
        mask_ref = params.get("maskNodeId")
        if not mask_ref:
            continue
        mask_key = str(mask_ref)
        if mask_key not in mask_capable:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'Node "{_resolve_node_id(node, consumer_index)}" references a non-mask output '
                    f'("{mask_key}"). Start from make_mask or from a branch forked from a mask output.'
                ),
            )
    return ordered


def _validate_branch_sources(
    pipeline_nodes: List[Dict[str, Any]],
    branch_sources_raw: Dict[str, Any],
) -> Dict[str, str]:
    """Resolve per-branch entry: 'original' or a node id. Unknown ids fall back to 'original'."""
    n = len(pipeline_nodes)
    id_to_index = {_resolve_node_id(pipeline_nodes[i], i): i for i in range(n)}

    branches_present: set[str] = set()
    for node in pipeline_nodes:
        branches_present.add(str(node.get("branch", "main")).strip() or "main")

    resolved: Dict[str, str] = {}
    raw = branch_sources_raw or {}

    for branch in branches_present:
        if branch == "main":
            resolved["main"] = "original"
            continue

        entry = raw.get(branch)
        if entry is None or str(entry).strip() == "":
            resolved[branch] = "original"
            continue

        src = str(entry).strip()
        if src.lower() == "original":
            resolved[branch] = "original"
            continue

        if src not in id_to_index:
            resolved[branch] = "original"
            continue

        resolved[branch] = src

    return resolved


def run_pipeline_pass(
    image: Image.Image,
    pipeline_nodes: List[Dict[str, Any]],
    branch_sources: Dict[str, str],
) -> Tuple[Image.Image, Dict[str, Image.Image]]:
    original_rgb = image.convert("RGB")
    branch_images: Dict[str, Image.Image] = {"main": original_rgb.copy()}
    node_outputs: Dict[str, Image.Image] = {}

    node_id_is_mask_capable: Dict[str, bool] = {}
    branch_is_mask: Dict[str, bool] = {"main": False}
    node_id_to_type: Dict[str, str] = {}
    for idx, pn in enumerate(pipeline_nodes):
        nid = _resolve_node_id(pn, idx)
        node_id_to_type[nid] = str(pn.get("type") or "")

    for index, node in enumerate(pipeline_nodes):
        node_id = _resolve_node_id(node, index)
        node_type = node.get("type")
        params = node.get("params", {})
        branch = str(node.get("branch", "main")).strip() or "main"
        if branch not in branch_images:
            src = branch_sources.get(branch, "original")
            if src == "original":
                branch_images[branch] = original_rgb.copy()
                branch_is_mask[branch] = False
            else:
                fork_from = node_outputs.get(src)
                if fork_from is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f'Branch "{branch}": entry source node "{src}" is not available yet '
                            "(must run before the first node of this branch)."
                        ),
                    )
                branch_images[branch] = fork_from.copy()
                branch_is_mask[branch] = node_id_is_mask_capable.get(src, False)

        try:
            effect_node = create_node(node_type, params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        before = branch_images[branch]
        effected = effect_node.apply(before)

        if node_type == "make_mask":
            branch_images[branch] = effected.convert("L")
            node_outputs[node_id] = branch_images[branch]
            node_id_is_mask_capable[node_id] = True
            branch_is_mask[branch] = True
            continue

        mask_node_id = params.get("maskNodeId")
        if mask_node_id:
            mask_key = str(mask_node_id)
            if not node_id_is_mask_capable.get(mask_key, False):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f'Node "{node_id}" references a non-mask output ("{mask_key}"). '
                        "Start from make_mask or from a branch forked from a mask output."
                    ),
                )
            selected_mask = node_outputs.get(mask_key)
            if selected_mask is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mask node not available yet (invalid order): {mask_node_id}",
                )

            mask_image = selected_mask.convert("L").resize(before.size)
            branch_images[branch] = Image.composite(
                effected.convert("RGB"),
                before.convert("RGB"),
                mask_image,
            )
        else:
            branch_images[branch] = effected
        node_outputs[node_id] = branch_images[branch]
        node_id_is_mask_capable[node_id] = branch_is_mask.get(branch, False)

    return branch_images["main"].convert("RGB"), node_outputs


def process_pipeline(
    image: Image.Image,
    pipeline_nodes: List[Dict[str, Any]],
    branch_sources_raw: Dict[str, Any] | None = None,
) -> Tuple[Image.Image, Dict[str, Image.Image]]:
    resolved_sources = _validate_branch_sources(pipeline_nodes, branch_sources_raw or {})
    ordered = order_pipeline_nodes(pipeline_nodes, resolved_sources)
    return run_pipeline_pass(image=image, pipeline_nodes=ordered, branch_sources=resolved_sources)


@app.post("/process-image")
async def process_image(
    image: UploadFile = File(...),
    pipeline: str = Form(...),
    preview_node_id: str | None = Form(default=None),
) -> StreamingResponse:
    try:
        parsed = json.loads(pipeline)
        nodes = parsed.get("nodes", [])
        branch_sources_raw = parsed.get("branchSources") or parsed.get("branch_sources") or {}
        if not isinstance(branch_sources_raw, dict):
            branch_sources_raw = {}
        if not isinstance(nodes, list):
            raise ValueError("pipeline.nodes must be a list")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline payload: {exc}") from exc

    raw = await image.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds maximum size ({_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB).",
        )

    input_image = _open_validated_upload(raw, image)

    final_image, node_outputs = process_pipeline(input_image, nodes, branch_sources_raw)
    output_image = final_image
    if preview_node_id:
        output_image = node_outputs.get(preview_node_id, final_image)

    out_buffer = io.BytesIO()
    output_image.save(out_buffer, format="PNG")
    out_buffer.seek(0)

    return StreamingResponse(out_buffer, media_type="image/png")
