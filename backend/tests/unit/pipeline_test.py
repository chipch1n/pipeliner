import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from backend.app.main import (
    process_pipeline,
    normalized_part_content_type,
    open_validated_upload,
    resolve_node_id,
    first_flat_index_for_branch,
    branches_in_pipeline,
    mask_capable_node_ids,
    order_pipeline_nodes,
    validate_branch_sources,
    run_pipeline_pass,
)

@pytest.fixture
def test_image():
    img = Image.new("RGB", (10, 10), color="red")
    return img

@pytest.fixture
def test_image_bytes(test_image):
    buf = io.BytesIO()
    test_image.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

class TestPipelineHelpers:
    def test_resolve_node_id(self):
        node = {"id": "myId"}
        assert resolve_node_id(node, 0) == "myId"
        node_no_id = {}
        assert resolve_node_id(node_no_id, 5) == "node-5"

    def test_first_flat_index_for_branch(self):
        nodes = [
            {"type": "blur", "branch": "main"},
            {"type": "noise", "branch": "side"},
            {"type": "blur", "branch": "main"},
        ]

        assert first_flat_index_for_branch(nodes, "side") == 1
        assert first_flat_index_for_branch(nodes, "main") == 0
        assert first_flat_index_for_branch(nodes, "nonexistent") == -1

    def test_branches_in_pipeline(self):
        nodes = [
            {"branch": "main"},
            {"branch": "side"},
            {"branch": "side"},
            {},
        ]

        branches = branches_in_pipeline(nodes)

        assert branches == {"main", "side"}

    def test_mask_capable_node_ids(self):
        nodes = [
            {"id": "1", "type": "blur"},
            {"id": "2", "type": "make_mask"},
            {"id": "3", "type": "blur", "branch": "side"},
            {"id": "4", "type": "noise", "branch": "side"},
        ]

        mask_ids = mask_capable_node_ids(nodes)
        assert mask_ids == {"2"}

        nodes2 = [
            {"id": "a", "type": "make_mask"},
            {"id": "b", "type": "blur", "branch": "new_branch"},
            {"id": "c", "type": "noise", "branch": "new_branch"},
        ]
        branch_sources = {"new_branch": "a"}

        mask_ids2 = mask_capable_node_ids(nodes2, branch_sources)

        assert mask_ids2 == {"a", "b", "c"}

class TestOrderPipelineNodes:
    def test_empty_pipeline(self):
        assert order_pipeline_nodes([]) == []

    def test_single_node(self):
        nodes = [{"type": "blur"}]

        ordered = order_pipeline_nodes(nodes)

        assert ordered == nodes

    def test_unconnected_nodes_preserve_order(self):
        nodes = [
            {"id": "2", "type": "noise"},
            {"id": "1", "type": "blur"},
        ]

        ordered = order_pipeline_nodes(nodes)

        assert [n["id"] for n in ordered] == ["2", "1"]

    def test_duplicate_ids_raise(self):
        nodes = [
            {"id": "dup", "type": "blur"},
            {"id": "dup", "type": "noise"},
        ]

        with pytest.raises(Exception) as exc:
            order_pipeline_nodes(nodes)

        assert exc.value.status_code == 400
        assert "Duplicate" in exc.value.detail

    def test_mask_dependency_topological(self):
        nodes = [
            {"id": "mask", "type": "make_mask"},
            {"id": "user", "type": "blur", "params": {"maskNodeId": "mask"}},
        ]

        ordered = order_pipeline_nodes(nodes)

        assert ordered[0]["id"] == "mask"
        assert ordered[1]["id"] == "user"

    def test_self_referencing_mask_raises(self):
        nodes = [
            {"id": "self", "type": "blur", "params": {"maskNodeId": "self"}},
        ]

        with pytest.raises(Exception) as exc:
            order_pipeline_nodes(nodes)

        assert exc.value.status_code == 400

    def test_missing_mask_node_raises(self):
        nodes = [
            {"id": "user", "type": "blur", "params": {"maskNodeId": "ghost"}},
        ]

        with pytest.raises(Exception) as exc:
            order_pipeline_nodes(nodes)

        assert exc.value.status_code == 400
        assert "Mask node id not found" in exc.value.detail

    def test_branch_entry_dependency(self):
        nodes = [
            {"id": "1", "type": "blur"},
            {"id": "2", "type": "noise", "branch": "side"},
            {"id": "3", "type": "blur", "branch": "side"},
        ]
        branch_sources = {"side": "1"}

        ordered = order_pipeline_nodes(nodes, branch_sources)

        assert ordered[0]["id"] == "1"
        assert ordered[1]["id"] == "2"
        assert ordered[2]["id"] == "3"

    def test_cycle_detection(self):
        nodes = [
            {"id": "a", "type": "blur", "params": {"maskNodeId": "b"}},
            {"id": "b", "type": "blur", "params": {"maskNodeId": "a"}},
        ]

        with pytest.raises(Exception) as exc:
            order_pipeline_nodes(nodes)

        assert exc.value.status_code == 400
        assert "Cycle" in exc.value.detail

    def test_mask_capability_validation(self):
        nodes = [
            {"id": "src", "type": "blur"},
            {"id": "dest", "type": "blur", "params": {"maskNodeId": "src"}},
        ]

        with pytest.raises(Exception) as exc:
            order_pipeline_nodes(nodes, validate_mask_providers=True)

        assert exc.value.status_code == 400
        assert "references a non-mask output" in exc.value.detail

class TestValidateBranchSources:
    def test_default_main(self):
        nodes = [{"branch": "main"}, {"branch": "side"}]

        sources = validate_branch_sources(nodes, {})

        assert sources == {"main": "original", "side": "original"}

    def test_explicit_branch_source(self):
        nodes = [{"id": "n1", "branch": "main"}, {"id": "n2", "branch": "side"}]
        raw = {"side": "n1"}

        sources = validate_branch_sources(nodes, raw)

        assert sources["main"] == "original"
        assert sources["side"] == "n1"

    def test_unknown_source_falls_back_to_original(self):
        nodes = [{"id": "n2", "branch": "side"}]
        raw = {"side": "ghost"}

        sources = validate_branch_sources(nodes, raw)

        assert sources["side"] == "original"

    def test_original_keyword(self):
        nodes = [{"id": "n2", "branch": "side"}]
        raw = {"side": "original"}

        sources = validate_branch_sources(nodes, raw)

        assert sources["side"] == "original"

class TestProcessPipelineIntegration:
    def test_smoke(self, test_image):
        nodes = [{"type": "blur"}]

        final, outputs = process_pipeline(test_image, nodes)

        assert isinstance(final, Image.Image)

    def test_branch_sources_are_resolved(self, test_image):
        nodes = [
            {"id": "blur1", "type": "blur"},
            {"id": "noise1", "type": "noise", "branch": "alt", "params": {"intensity": 10}},
            {"id": "blur2", "type": "blur", "branch": "alt"},
        ]
        branch_sources = {"alt": "blur1"}

        final, outputs = process_pipeline(test_image.copy(), nodes, branch_sources)

        assert "blur1" in outputs
        assert "noise1" in outputs
        assert "blur2" in outputs
        assert final.size == test_image.size

class TestImageValidation:
    def test_normalized_part_content_type(self):
        upload = MagicMock()
        upload.content_type = "image/png; charset=utf-8"
        assert normalized_part_content_type(upload) == "image/png"
        upload.content_type = "image/jpeg"
        assert normalized_part_content_type(upload) == "image/jpeg"
        upload.content_type = None
        assert normalized_part_content_type(upload) == ""

    def test_open_validated_upload_valid(self, test_image_bytes):
        upload = MagicMock()
        upload.content_type = "image/png"
        upload.filename = "test.png"

        img = open_validated_upload(test_image_bytes, upload)

        assert isinstance(img, Image.Image)
        assert img.format == "PNG"

    def test_open_validated_upload_wrong_content_type(self, test_image_bytes):
        upload = MagicMock()
        upload.content_type = "image/gif"
        upload.filename = "test.png"

        with pytest.raises(Exception) as exc:
            open_validated_upload(test_image_bytes, upload)

        assert exc.value.status_code == 400
        assert "Content-Type does not match" in exc.value.detail

    def test_open_validated_upload_empty(self):
        upload = MagicMock()

        with pytest.raises(Exception) as exc:
            open_validated_upload(b"", upload)

        assert exc.value.status_code == 400
        assert "empty" in exc.value.detail

class TestRunPipelinePass:
    def test_simple_blur(self, test_image):
        nodes = [{"type": "blur", "params": {"radius": 5}}]

        final, outputs = run_pipeline_pass(test_image, nodes, {"main": "original"})

        assert isinstance(final, Image.Image)
        assert final.size == test_image.size

    def test_blur_with_mask(self, test_image):
        nodes = [
            {"id": "mask", "type": "make_mask", "params": {"threshold": 100}},
            {"id": "blurred", "type": "blur", "params": {"radius": 10, "maskNodeId": "mask"}},
        ]

        final, outputs = run_pipeline_pass(test_image.copy(), nodes, {"main": "original"})

        assert final.mode == "RGB"

    def test_branch_fork_from_output(self, test_image):
        nodes = [
            {"id": "1", "type": "blur", "params": {"radius": 5}},
            {"id": "2", "type": "noise", "branch": "side", "params": {"intensity": 10}},
            {"id": "3", "type": "blur", "branch": "side", "params": {"radius": 2}},
        ]
        branch_sources = {"side": "1"}

        final, outputs = run_pipeline_pass(test_image.copy(), nodes, branch_sources)

        assert final.size == test_image.size
        assert "1" in outputs
        assert "2" in outputs
        assert "3" in outputs

    def test_branch_source_not_available_raises(self, test_image):
        nodes = [
            {"id": "1", "type": "blur"},
            {"id": "2", "type": "noise", "branch": "side"},
        ]
        branch_sources = {"side": "3"}

        with pytest.raises(Exception) as exc:
            run_pipeline_pass(test_image, nodes, branch_sources)

        assert exc.value.status_code == 400
        assert "is not available yet" in exc.value.detail

    def test_invalid_mask_node_raises(self, test_image):
        nodes = [
            {"id": "src", "type": "blur"},
            {"id": "dest", "type": "blur", "params": {"maskNodeId": "src"}},
        ]

        with pytest.raises(Exception) as exc:
            run_pipeline_pass(test_image, nodes, {"main": "original"})

        assert exc.value.status_code == 400

    def test_skip_hf_skips_debug_node_without_cache(self):
        image = Image.new("RGB", (10, 10), color=(0, 0, 255))
        nodes = [
            {"id": "hf", "type": "hf_image_to_image", "params": {"model": "x/y", "debug": True}},
        ]

        final, outputs = run_pipeline_pass(
            image,
            nodes,
            {"main": "original"},
            skip_node_types={"hf_image_to_image"},
        )

        assert outputs["hf"].getpixel((0, 0)) == (0, 0, 255)
        assert final.getpixel((0, 0)) == (0, 0, 255)

    def test_skip_hf_uses_cached_output_for_downstream(self, test_image):
        hf_cached = Image.new("RGB", test_image.size, color=(0, 255, 0))
        nodes = [
            {"id": "blur", "type": "blur", "params": {"radius": 5}},
            {"id": "hf", "type": "hf_image_to_image", "params": {"model": "x/y"}},
            {"id": "noise", "type": "noise", "params": {"intensity": 100, "seed": 1}},
        ]

        without_cache, _ = run_pipeline_pass(
            test_image.copy(),
            nodes,
            {"main": "original"},
            skip_node_types={"hf_image_to_image"},
        )
        with_cache, outputs = run_pipeline_pass(
            test_image.copy(),
            nodes,
            {"main": "original"},
            skip_node_types={"hf_image_to_image"},
            cached_node_outputs={"hf": hf_cached},
        )

        assert outputs["hf"].getpixel((0, 0)) == (0, 255, 0)
        assert without_cache.tobytes() != with_cache.tobytes()