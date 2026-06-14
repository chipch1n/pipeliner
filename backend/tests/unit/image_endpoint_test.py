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