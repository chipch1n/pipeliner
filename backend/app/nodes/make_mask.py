from PIL import Image, ImageOps

from .base import BaseNode


class MakeMaskNode(BaseNode):
    def apply(self, image: Image.Image) -> Image.Image:
        threshold = int(self.params.get("threshold", 128))
        threshold = max(0, min(threshold, 255))
        invert = bool(self.params.get("invert", False))

        grayscale = image.convert("L")
        mask = grayscale.point(lambda px: 255 if px >= threshold else 0)
        if invert:
            mask = ImageOps.invert(mask)
        return mask
