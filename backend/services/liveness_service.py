"""
Passive liveness using Silent-Face-Anti-Spoof ONNX (MiniFASNet / CDNet-style).
Preprocessing matches common 80x80 RGB + CHW float32 [0,1].

Place ONNX weights at ANTI_SPOOF_ONNX_PATH (see README).
If the file is missing, the service reports unavailable (503) instead of crashing.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

from config import get_settings
from services import face_service

LOGGER = logging.getLogger(__name__)
settings = get_settings()

_session_lock = threading.Lock()
_onnx_session: ort.InferenceSession | None = None
_input_name: str | None = None
_model_loaded: bool = False
_load_error: str | None = None


def _get_session() -> tuple[ort.InferenceSession | None, str | None, str | None]:
    global _onnx_session, _input_name, _model_loaded, _load_error
    if _model_loaded:
        return _onnx_session, _input_name, _load_error
    with _session_lock:
        if _model_loaded:
            return _onnx_session, _input_name, _load_error
        path = os.path.abspath(settings.ANTI_SPOOF_ONNX_PATH)
        if not os.path.isfile(path):
            _load_error = f"Anti-spoof ONNX not found at {path}"
            _model_loaded = True
            LOGGER.warning(_load_error)
            return None, None, _load_error
        try:
            sess = ort.InferenceSession(
                path,
                providers=["CPUExecutionProvider"],
            )
            inp = sess.get_inputs()[0]
            _onnx_session = sess
            _input_name = inp.name
            _model_loaded = True
            LOGGER.info("Anti-spoof ONNX loaded from %s", path)
            return _onnx_session, _input_name, None
        except Exception as exc:
            msg = str(exc)
            if ".onnx.data" in msg:
                _load_error = (
                    "ONNX model uses external tensor data, but companion '.onnx.data' file is missing. "
                    f"Expected near: {path}.data"
                )
            else:
                _load_error = msg
            _model_loaded = True
            LOGGER.exception("Failed to load anti-spoof ONNX.")
            return None, None, _load_error


def is_liveness_available() -> bool:
    sess, _, err = _get_session()
    return sess is not None and err is None


def should_use_dev_fallback() -> bool:
    return bool(settings.DEV_ALLOW_LIVENESS_FALLBACK and not is_liveness_available())


def preprocess_face_bgr(bgr: np.ndarray, size: int = 80) -> np.ndarray:
    """Resize to size x size and normalize for anti-spoof model."""
    resized = cv2.resize(bgr, (size, size), interpolation=cv2.INTER_AREA)
    if settings.LIVENESS_USE_RGB_INPUT:
        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    t = resized.astype(np.float32)
    if settings.LIVENESS_INPUT_NORM == "silent_face":
        t = (t - 127.5) / 128.0
    else:
        t = t / 255.0
    t = np.transpose(t, (2, 0, 1))
    return np.expand_dims(t, axis=0)


def _extract_face_roi_bgr(frame_bgr: np.ndarray) -> np.ndarray:
    """
    Extract largest face ROI for anti-spoof scoring.
    Falls back to full frame if detector backend is unavailable.
    """
    try:
        app = face_service.get_face_analyzer()
        h, w = frame_bgr.shape[:2]

        backend = face_service.get_face_backend_name()
        if backend == "insightface":
            faces = app.get(frame_bgr)
            if not faces:
                return frame_bgr
            best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            x1, y1, x2, y2 = [int(v) for v in best.bbox]
        elif backend == "facenet":
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            boxes, _probs = app["detector"].detect(Image.fromarray(rgb))
            if boxes is None or len(boxes) == 0:
                return frame_bgr
            areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
            box = boxes[int(np.argmax(np.asarray(areas)))]
            x1, y1, x2, y2 = [int(v) for v in box]
        else:
            return frame_bgr

        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        mx = int(bw * settings.LIVENESS_FACE_CROP_MARGIN)
        my = int(bh * settings.LIVENESS_FACE_CROP_MARGIN)
        x1 = max(0, x1 - mx)
        y1 = max(0, y1 - my)
        x2 = min(w, x2 + mx)
        y2 = min(h, y2 + my)
        if x2 <= x1 or y2 <= y1:
            return frame_bgr
        roi = frame_bgr[y1:y2, x1:x2]
        return roi if roi.size else frame_bgr
    except Exception:
        return frame_bgr


def predict_liveness_score(bgr: np.ndarray) -> tuple[float | None, str | None]:
    """
    Returns (live_probability in [0,1], error_message).
    Uses argmax softmax: class 0 = real for 2-class MiniFASNet exports.
    """
    sess, in_name, err = _get_session()
    if sess is None or in_name is None:
        if should_use_dev_fallback():
            # Dev fallback: lets frontend flow continue when ONNX model is absent.
            # Returns strong live score intentionally; never enable in production.
            LOGGER.warning("Using dev liveness fallback (ONNX missing).")
            return 0.99, None
        return None, err or "Liveness model unavailable."

    try:
        inp = sess.get_inputs()[0]
        shape = inp.shape
        # Dynamic batch / spatial — infer size from model if static
        h = w = 80
        if len(shape) == 4 and shape[2] not in (-1, None) and shape[3] not in (-1, None):
            h, w = int(shape[2]), int(shape[3])
        elif len(shape) == 4 and isinstance(shape[2], int) and shape[2] > 0:
            h = w = int(shape[2])

        roi = _extract_face_roi_bgr(bgr)
        x = preprocess_face_bgr(roi, size=h)
        out = sess.run(None, {in_name: x})
        logits = np.asarray(out[0]).reshape(-1)
        # Softmax
        e = np.exp(logits - np.max(logits))
        prob = e / (np.sum(e) + 1e-8)
        if settings.LIVENESS_DEBUG_LOG_PROBS:
            LOGGER.info("Liveness probs=%s logits=%s", prob.tolist(), logits.tolist())
        if prob.size >= 2:
            idx = int(max(0, min(prob.size - 1, settings.LIVENESS_LIVE_CLASS_INDEX)))
            mode = (settings.LIVENESS_SCORE_MODE or "index").strip().lower()
            if mode == "one_minus_index":
                live_prob = float(1.0 - prob[idx])
            elif mode == "sum_except_index":
                live_prob = float(np.sum(prob) - prob[idx])
            else:
                live_prob = float(prob[idx])
            if settings.LIVENESS_DEBUG_LOG_PROBS:
                LOGGER.info(
                    "Liveness score mode=%s idx=%d live_prob=%.6f",
                    mode,
                    idx,
                    live_prob,
                )
        else:
            live_prob = float(prob[0])
        return live_prob, None
    except Exception as exc:
        LOGGER.exception("Liveness inference failed.")
        return None, str(exc)
