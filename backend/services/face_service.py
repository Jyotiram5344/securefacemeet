"""
Face detection + ArcFace embedding via InsightFace.
Singleton model — loaded once per worker process.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import threading
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image

# Globally disable PyTorch autograd gradients and configure minimal concurrency to prevent OOM
torch.set_grad_enabled(False)
torch.set_num_threads(1)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass

from config import get_settings

LOGGER = logging.getLogger(__name__)
settings = get_settings()

_face_lock = threading.Lock()
_face_app: Any = None
_face_backend: str | None = None


class FaceServiceUnavailable(RuntimeError):
    """Raised when face recognition backend dependencies are unavailable."""


def _ctx_id() -> int:
    """Use GPU if CUDA available; else CPU."""
    try:
        import torch

        return 0 if torch.cuda.is_available() else -1
    except Exception:
        return -1


def get_face_analyzer() -> Any:
    global _face_app
    global _face_backend
    if _face_app is not None:
        return _face_app
    with _face_lock:
        if _face_app is not None:
            return _face_app
        try:
            from insightface.app import FaceAnalysis

            root = os.path.expanduser(settings.INSIGHTFACE_ROOT)
            app = FaceAnalysis(
                name=settings.INSIGHTFACE_MODEL_NAME,
                root=root,
            )
            app.prepare(ctx_id=_ctx_id(), det_size=(640, 640))
            _face_app = app
            _face_backend = "insightface"
            LOGGER.info("Face backend loaded: insightface (%s)", settings.INSIGHTFACE_MODEL_NAME)
            return _face_app
        except Exception as insight_err:
            LOGGER.warning("InsightFace unavailable, switching to facenet-pytorch: %s", insight_err)
            try:
                from facenet_pytorch import InceptionResnetV1, MTCNN

                torch.set_num_threads(1)
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                mtcnn = MTCNN(
                    image_size=160,
                    margin=0,
                    keep_all=True,
                    post_process=True,
                    device=device,
                )
                embedder = InceptionResnetV1(pretrained="vggface2").eval().to(device)
                _face_app = {"detector": mtcnn, "embedder": embedder, "device": device}
                _face_backend = "facenet"
                LOGGER.info("Face backend loaded: facenet-pytorch (vggface2)")
                return _face_app
            except Exception as facenet_err:
                raise FaceServiceUnavailable(
                    f"No usable face backend. InsightFace error: {insight_err}. "
                    f"Facenet error: {facenet_err}"
                ) from facenet_err


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


def get_face_backend_name() -> str | None:
    return _face_backend


def count_faces_bgr(bgr: np.ndarray) -> int | None:
    """
    Number of detected faces using the configured backend.
    Returns None if inference failed (caller may treat as indeterminate/fail closed).
    """
    if bgr is None or bgr.size == 0:
        return None
    try:
        app = get_face_analyzer()
        backend = get_face_backend_name()
        candidates: list[np.ndarray] = [bgr]

        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        enhanced = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        candidates.append(enhanced)

        max_count = 0
        if backend == "insightface":
            for cand in candidates:
                faces = app.get(cand)
                max_count = max(max_count, len(faces) if faces is not None else 0)
            return int(max_count)

        if backend == "facenet":
            detector = app["detector"]
            for cand in candidates:
                rgb = cv2.cvtColor(cand, cv2.COLOR_BGR2RGB)
                boxes, _probs = detector.detect(Image.fromarray(rgb))
                if boxes is None:
                    continue
                max_count = max(max_count, int(len(boxes)))
            return int(max_count)
    except FaceServiceUnavailable:
        raise
    except Exception:
        LOGGER.exception("count_faces_bgr failed.")
        return None
    return None


def detect_primary_face_landmarks_bgr(bgr: np.ndarray) -> dict[str, np.ndarray] | None:
    """
    Return landmarks for the largest detected face:
    keys: left_eye, right_eye, nose.
    """
    if bgr is None or bgr.size == 0:
        return None
    app = get_face_analyzer()
    backend = get_face_backend_name()

    if backend == "insightface":
        faces = app.get(bgr)
        if not faces:
            return None
        best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        kps = np.asarray(best.kps, dtype=np.float32)
        if kps.shape[0] < 3:
            return None
        if kps.shape[0] >= 5:
            return {
                "left_eye": kps[0],
                "right_eye": kps[1],
                "nose": kps[2],
                "mouth_left": kps[3],
                "mouth_right": kps[4],
            }
        return {"left_eye": kps[0], "right_eye": kps[1], "nose": kps[2]}

    if backend == "facenet":
        detector = app["detector"]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        boxes, _probs, points = detector.detect(Image.fromarray(rgb), landmarks=True)
        if boxes is None or points is None or len(boxes) == 0:
            return None
        areas = np.asarray([(b[2] - b[0]) * (b[3] - b[1]) for b in boxes], dtype=np.float32)
        idx = int(np.argmax(areas))
        lm = np.asarray(points[idx], dtype=np.float32)
        
        # Clean up temporary objects to prevent OOM
        del rgb, boxes, _probs, points
        gc.collect()

        if lm.shape[0] < 3:
            return None
        if lm.shape[0] >= 5:
            return {
                "left_eye": lm[0],
                "right_eye": lm[1],
                "nose": lm[2],
                "mouth_left": lm[3],
                "mouth_right": lm[4],
            }
        return {"left_eye": lm[0], "right_eye": lm[1], "nose": lm[2]}

    return None


def extract_embedding_bgr(bgr: np.ndarray) -> np.ndarray | None:
    """
    Return L2-normalized 512-D ArcFace embedding, or None if no face.
    """
    if bgr is None or bgr.size == 0:
        return None
    try:
        app = get_face_analyzer()
        candidates: list[np.ndarray] = [bgr]

        # Retry with contrast/brightness normalization for low-light uploads.
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        enhanced = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        candidates.append(enhanced)
        candidates.append(cv2.convertScaleAbs(enhanced, alpha=1.2, beta=8))

        # Retry at different scales to reduce detector misses.
        h, w = bgr.shape[:2]
        if min(h, w) < 720:
            candidates.append(cv2.resize(bgr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC))
        candidates.append(cv2.resize(bgr, (max(160, w // 2), max(160, h // 2)), interpolation=cv2.INTER_AREA))

        for candidate in candidates:
            if _face_backend == "insightface":
                faces = app.get(candidate)
                if not faces:
                    continue
                best = max(
                    faces,
                    key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                )
                emb = best.embedding.astype(np.float32)
                norm = np.linalg.norm(emb) + 1e-8
                return (emb / norm).astype(np.float32)

            if _face_backend == "facenet":
                detector = app["detector"]
                embedder = app["embedder"]
                device = app["device"]
                rgb = cv2.cvtColor(candidate, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
                boxes, _probs = detector.detect(pil)
                if boxes is None or len(boxes) == 0:
                    continue
                areas = [(box[2] - box[0]) * (box[3] - box[1]) for box in boxes]
                best_idx = int(np.argmax(np.asarray(areas)))

                crops = detector(pil)
                if crops is None:
                    continue
                if len(crops.shape) == 3:
                    crops = crops.unsqueeze(0)
                if crops.shape[0] <= best_idx:
                    best_idx = 0
                face_tensor = crops[best_idx].unsqueeze(0).to(device)
                emb_tensor = embedder(face_tensor)
                emb = emb_tensor.squeeze(0).detach().cpu().numpy().astype(np.float32)
                norm = np.linalg.norm(emb) + 1e-8
                result = (emb / norm).astype(np.float32)
                
                # Explicitly clean up large PyTorch tensors to prevent OOM
                del face_tensor, emb_tensor, crops, pil, rgb
                gc.collect()
                return result
        return None
    except FaceServiceUnavailable:
        raise
    except Exception:
        LOGGER.exception("Face embedding extraction failed.")
        return None
    finally:
        gc.collect()


def embedding_to_json(emb: np.ndarray) -> str:
    return json.dumps(emb.astype(float).tolist())


def json_to_embedding(s: str) -> np.ndarray:
    data = json.loads(s)
    return np.asarray(data, dtype=np.float32)
