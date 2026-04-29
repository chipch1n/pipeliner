from PIL import Image, ImageFilter

from .base import BaseNode


class BlurNode(BaseNode):
    def apply(self, image: Image.Image) -> Image.Image:
        radius = float(self.params.get("radius", 2))
        radius = max(0.0, min(radius, 50.0))
        return image.filter(ImageFilter.GaussianBlur(radius=radius))
