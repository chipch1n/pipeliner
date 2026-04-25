from abc import ABC, abstractmethod
from typing import Any, Dict

from PIL import Image


class BaseNode(ABC):
    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.params = params or {}

    @abstractmethod
    def apply(self, image: Image.Image) -> Image.Image:
        raise NotImplementedError
