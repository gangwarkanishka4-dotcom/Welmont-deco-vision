"""GPU/CPU auto-detection shared by every model wrapper."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_device(requested: str) -> str:
    """requested is 'auto' | 'cpu' | 'cuda' | 'cuda:N'. Returns a torch-compatible device string."""
    if requested != "auto":
        return requested

    try:
        import torch

        if torch.cuda.is_available():
            logger.info("CUDA available — using GPU device cuda:0")
            return "cuda:0"
    except ImportError:
        pass

    logger.info("CUDA not available — falling back to CPU")
    return "cpu"
