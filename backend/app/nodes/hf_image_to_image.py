import io
import logging
import os

from PIL import Image, ImageDraw

from .base import BaseNode

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Qwen/Qwen-Image-Edit-2511"
DEFAULT_PROMPT = "enhance the image"
DEFAULT_PROVIDER = "fal-ai"
HF_TIMEOUT_SEC = 120


def _hf_token() -> str | None:
    raw = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _is_debug(params: dict) -> bool:
    raw = params.get("debug")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return raw in (1,)


def apply_debug_overlay(image: Image.Image) -> Image.Image:
    """Local stand-in for HF inference — red square top-left, no API call."""
    out = image.convert("RGB")
    w, h = out.size
    side = max(16, min(w, h) // 4)
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, 0, side - 1, side - 1], fill=(255, 0, 0))
    return out


def _friendly_hf_error(exc: Exception) -> str:
    msg = str(exc)
    if "sufficient permissions" in msg.lower() or "inference providers" in msg.lower():
        return (
            "Hugging Face Inference Providers rejected this token (403). "
        )
    return f"Hugging Face image_to_image failed: {exc}"


class HfImageToImageNode(BaseNode):
    """Runs a Hugging Face Inference Providers image-to-image model on the branch image."""

    def apply(self, image: Image.Image) -> Image.Image:
        if _is_debug(self.params):
            logger.info("hf_image_to_image: debug mode — skipping Hugging Face API")
            return apply_debug_overlay(image)

        model = str(self.params.get("model") or DEFAULT_MODEL).strip()
        if not model:
            raise ValueError("hf_image_to_image: model is required")

        prompt = str(self.params.get("prompt") if self.params.get("prompt") is not None else DEFAULT_PROMPT)
        prompt = prompt.strip() or DEFAULT_PROMPT

        provider = str(self.params.get("provider") or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER

        token = _hf_token()
        if not token:
            raise ValueError(
                "hf_image_to_image: set HF_TOKEN or HUGGINGFACE_HUB_TOKEN for Hugging Face Inference"
            )

        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise ValueError("hf_image_to_image: huggingface_hub is not installed") from exc

        client = InferenceClient(provider=provider, token=token, timeout=HF_TIMEOUT_SEC)

        rgb = image.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")

        call_kwargs: dict = {"prompt": prompt, "model": model}
        extra = self.params.get("extra")
        if isinstance(extra, dict):
            call_kwargs.update(extra)

        try:
            result = client.image_to_image(buf.getvalue(), **call_kwargs)
        except Exception as exc:
            logger.warning("HF image_to_image failed model=%s provider=%s: %s", model, provider, exc)
            detail = _friendly_hf_error(exc)
            raise ValueError(detail) from exc

        if isinstance(result, Image.Image):
            return result.convert("RGB")

        raise ValueError("hf_image_to_image: unexpected response type from Hugging Face")
