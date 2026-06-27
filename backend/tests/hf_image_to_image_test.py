from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from backend.app.nodes.factory import create_node
from backend.app.nodes.hf_image_to_image import HfImageToImageNode, apply_debug_overlay


@pytest.fixture
def solid_image():
    return Image.new("RGB", (32, 32), color=(100, 150, 200))


class TestHfImageToImageNode:
    def test_missing_token_raises(self, solid_image, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
        node = HfImageToImageNode({"model": "org/model", "prompt": "test"})
        with pytest.raises(ValueError, match="HF_TOKEN"):
            node.apply(solid_image)

    @patch("huggingface_hub.InferenceClient")
    def test_apply_returns_rgb_from_client(self, mock_client_cls, solid_image, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "test-token")
        expected = Image.new("RGB", (32, 32), color=(1, 2, 3))
        mock_client = MagicMock()
        mock_client.image_to_image.return_value = expected
        mock_client_cls.return_value = mock_client

        node = HfImageToImageNode(
            {
                "model": "timbrooks/instruct-pix2pix",
                "prompt": "make it sketch",
                "provider": "replicate",
            }
        )
        result = node.apply(solid_image)

        assert result.mode == "RGB"
        assert result.size == expected.size
        mock_client_cls.assert_called_once_with(provider="replicate", token="test-token", timeout=120)
        mock_client.image_to_image.assert_called_once()
        call_args, call_kwargs = mock_client.image_to_image.call_args
        assert call_kwargs["model"] == "timbrooks/instruct-pix2pix"
        assert call_kwargs["prompt"] == "make it sketch"
        assert isinstance(call_args[0], bytes)

    @patch("huggingface_hub.InferenceClient")
    def test_hf_api_error_becomes_value_error(self, mock_client_cls, solid_image, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "test-token")
        mock_client = MagicMock()
        mock_client.image_to_image.side_effect = RuntimeError("503 model loading")
        mock_client_cls.return_value = mock_client

        node = HfImageToImageNode({"model": "org/model"})
        with pytest.raises(ValueError, match="image_to_image failed"):
            node.apply(solid_image)

    def test_empty_model_raises(self, solid_image, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "test-token")
        node = HfImageToImageNode({"model": "   "})
        with pytest.raises(ValueError, match="model is required"):
            node.apply(solid_image)

    def test_factory_registers_type(self):
        node = create_node("hf_image_to_image", {"model": "x/y"})
        assert isinstance(node, HfImageToImageNode)

    def test_debug_mode_adds_red_square_without_token(self, solid_image, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        node = HfImageToImageNode({"model": "org/model", "debug": True})
        result = node.apply(solid_image)
        assert result.getpixel((0, 0)) == (255, 0, 0)
        assert result.getpixel((solid_image.size[0] - 1, solid_image.size[1] - 1)) != (255, 0, 0)

    def test_debug_overlay_helper(self, solid_image):
        result = apply_debug_overlay(solid_image)
        assert result.getpixel((0, 0)) == (255, 0, 0)
