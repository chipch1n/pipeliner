from typing import Any, Dict, Type

from .base import BaseNode
from .blur import BlurNode
from .make_mask import MakeMaskNode
from .noise import NoiseNode

NODE_REGISTRY: Dict[str, Type[BaseNode]] = {
    "blur": BlurNode,
    "noise": NoiseNode,
    "make_mask": MakeMaskNode,
}


def create_node(node_type: str, params: Dict[str, Any]) -> BaseNode:
    node_class = NODE_REGISTRY.get(node_type)
    if not node_class:
        raise ValueError(f"Unsupported node type: {node_type}")
    return node_class(params)
