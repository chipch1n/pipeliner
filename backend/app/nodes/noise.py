import numpy as np
from PIL import Image

from .base import BaseNode


class NoiseNode(BaseNode):
    def apply(self, image: Image.Image) -> Image.Image:
        intensity = float(self.params.get("intensity", 20))
        intensity = max(0.0, min(intensity, 100.0))

        arr = np.array(image).astype(np.float32)
        noise = np.random.normal(0.0, intensity, arr.shape).astype(np.float32)
        out = np.clip(arr + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(out)
