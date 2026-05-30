import io
import json

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.main import (
    app,
    MAX_UPLOAD_BYTES,
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

@pytest.fixture
def test_client():
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

class TestProcessImageEndpoint:
    def test_success(self, test_client, test_image_bytes):
        pipeline = {"nodes": [{"type": "blur"}]}
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline)}

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        result_img = Image.open(io.BytesIO(response.content))
        assert result_img.format == "PNG"

    def test_preview_node(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "blur1", "type": "blur"},
                {"id": "noise1", "type": "noise"},
            ]
        }
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": json.dumps(pipeline), "preview_node_id": "blur1"}

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 200

    def test_invalid_pipeline(self, test_client, test_image_bytes):
        pipeline = "not a json"
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {"pipeline": pipeline}

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 400

    def test_oversized_image(self, test_client):
        large_data = b"x" * (MAX_UPLOAD_BYTES + 1)
        files = {"image": ("large.png", large_data, "image/png")}
        data = {"pipeline": json.dumps({"nodes": []})}

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 413

    def test_skip_node_types_skips_hf_inference(self, test_client):
        img = Image.new("RGB", (32, 32), color=(0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        pipeline = {
            "nodes": [
                {
                    "id": "hf",
                    "type": "hf_image_to_image",
                    "params": {"model": "x/y", "debug": True},
                }
            ]
        }
        files = {"image": ("test.png", image_bytes, "image/png")}
        data = {
            "pipeline": json.dumps(pipeline),
            "skip_node_types": json.dumps(["hf_image_to_image"]),
        }

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 200
        result = Image.open(io.BytesIO(response.content))
        assert result.getpixel((0, 0)) == (0, 0, 255)

    def test_cached_output_multipart_used_when_hf_skipped(self, test_client, test_image_bytes):
        cached = Image.new("RGB", (10, 10), color=(0, 255, 0))
        cached_buf = io.BytesIO()
        cached.save(cached_buf, format="PNG")
        cached_bytes = cached_buf.getvalue()

        pipeline = {
            "nodes": [
                {"id": "blur", "type": "blur", "params": {"radius": 5}},
                {"id": "hf", "type": "hf_image_to_image", "params": {"model": "x/y", "debug": True}},
                {"id": "noise", "type": "noise", "params": {"intensity": 100, "seed": 1}},
            ]
        }
        files = {
            "image": ("test.png", test_image_bytes, "image/png"),
            "cached_output:hf": ("hf.png", cached_bytes, "image/png"),
        }
        data = {
            "pipeline": json.dumps(pipeline),
            "skip_node_types": json.dumps(["hf_image_to_image"]),
        }

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 200
        without_cache = test_client.post(
            "/process-image",
            files={"image": ("test.png", test_image_bytes, "image/png")},
            data={
                "pipeline": json.dumps(pipeline),
                "skip_node_types": json.dumps(["hf_image_to_image"]),
            },
        )
        assert without_cache.status_code == 200
        assert response.content != without_cache.content

    def test_invalid_skip_node_types_returns_400(self, test_client, test_image_bytes):
        files = {"image": ("test.png", test_image_bytes, "image/png")}
        data = {
            "pipeline": json.dumps({"nodes": []}),
            "skip_node_types": "not-json",
        }

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 400
        assert "skip_node_types" in response.json()["detail"]

    def test_invalid_cached_output_returns_400(self, test_client, test_image_bytes):
        pipeline = {
            "nodes": [
                {"id": "hf", "type": "hf_image_to_image", "params": {"model": "x/y", "debug": True}},
            ]
        }
        files = {
            "image": ("test.png", test_image_bytes, "image/png"),
            "cached_output:hf": ("hf.bin", b"not-an-image", "application/octet-stream"),
        }
        data = {
            "pipeline": json.dumps(pipeline),
            "skip_node_types": json.dumps(["hf_image_to_image"]),
        }

        response = test_client.post("/process-image", files=files, data=data)

        assert response.status_code == 400
        assert "cached_output:hf" in response.json()["detail"]