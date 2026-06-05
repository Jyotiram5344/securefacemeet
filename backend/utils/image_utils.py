"""Decode uploads and prepare BGR/ RGB arrays for vision pipelines."""
from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image


def bytes_to_bgr(image_bytes: bytes) -> np.ndarray | None:
    """Decode image bytes to BGR uint8 (OpenCV convention)."""
    if not image_bytes:
        return None
    try:
        pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb = np.array(pil, dtype=np.uint8)
        # BGR for InsightFace / OpenCV
        bgr = rgb[:, :, ::-1].copy()
        return bgr
    except Exception:
        return None


def ensure_min_size(bgr: np.ndarray, min_side: int = 64) -> bool:
    h, w = bgr.shape[:2]
    return h >= min_side and w >= min_side


def base64_to_bgr(frame_b64: str, *, max_bytes: int) -> np.ndarray | None:
    if not frame_b64:
        return None
    try:
        payload = frame_b64.split(",", 1)[1] if "," in frame_b64 else frame_b64
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        return None
    if len(raw) > max_bytes:
        return None
    return bytes_to_bgr(raw)
