import io
import json
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image

from .nodes import create_node

app = FastAPI(title="Pipeliner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_pipeline_pass(
    image: Image.Image,
    pipeline_nodes: List[Dict[str, Any]],
    fallback_masks: Dict[str, Image.Image] | None = None,
    allow_missing_masks: bool = False,
) -> Tuple[Image.Image, Dict[str, Image.Image]]:
    branch_images: Dict[str, Image.Image] = {"main": image.convert("RGB")}
    node_outputs: Dict[str, Image.Image] = {}

    for index, node in enumerate(pipeline_nodes):
        node_id = str(node.get("id") or f"node-{index}")
        node_type = node.get("type")
        params = node.get("params", {})
        branch = str(node.get("branch", "main")).strip() or "main"
        if branch not in branch_images:
            branch_images[branch] = branch_images["main"].copy()

        try:
            effect_node = create_node(node_type, params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        before = branch_images[branch]
        effected = effect_node.apply(before)

        if node_type == "make_mask":
            branch_images[branch] = effected.convert("L")
            node_outputs[node_id] = branch_images[branch]
            continue

        mask_node_id = params.get("maskNodeId")
        if mask_node_id:
            mask_key = str(mask_node_id)
            selected_mask = node_outputs.get(mask_key)
            if selected_mask is None and fallback_masks:
                selected_mask = fallback_masks.get(mask_key)

            if selected_mask is None:
                if allow_missing_masks:
                    branch_images[branch] = effected
                    node_outputs[node_id] = branch_images[branch]
                    continue
                raise HTTPException(status_code=400, detail=f"Mask node not found: {mask_node_id}")

            mask_image = selected_mask.convert("L").resize(before.size)
            branch_images[branch] = Image.composite(
                effected.convert("RGB"),
                before.convert("RGB"),
                mask_image,
            )
        else:
            branch_images[branch] = effected
        node_outputs[node_id] = branch_images[branch]

    return branch_images["main"].convert("RGB"), node_outputs


def process_pipeline(image: Image.Image, pipeline_nodes: List[Dict[str, Any]]) -> Tuple[Image.Image, Dict[str, Image.Image]]:
    # Precompute all node outputs so masks can reference nodes across branches
    # even when they appear later in the linear execution order.
    _, precomputed_outputs = run_pipeline_pass(
        image=image,
        pipeline_nodes=pipeline_nodes,
        fallback_masks=None,
        allow_missing_masks=True,
    )

    return run_pipeline_pass(
        image=image,
        pipeline_nodes=pipeline_nodes,
        fallback_masks=precomputed_outputs,
        allow_missing_masks=False,
    )


@app.post("/process-image")
async def process_image(
    image: UploadFile = File(...),
    pipeline: str = Form(...),
    preview_node_id: str | None = Form(default=None),
) -> StreamingResponse:
    try:
        parsed = json.loads(pipeline)
        nodes = parsed.get("nodes", [])
        if not isinstance(nodes, list):
            raise ValueError("pipeline.nodes must be a list")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline payload: {exc}") from exc

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        input_image = Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc

    final_image, node_outputs = process_pipeline(input_image, nodes)
    output_image = final_image
    if preview_node_id:
        output_image = node_outputs.get(preview_node_id, final_image)

    out_buffer = io.BytesIO()
    output_image.save(out_buffer, format="PNG")
    out_buffer.seek(0)

    return StreamingResponse(out_buffer, media_type="image/png")
