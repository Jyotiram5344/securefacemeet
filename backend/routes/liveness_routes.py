"""Passive liveness (anti-spoof) endpoint."""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status

from config import get_settings
from services import auth_service, face_service, liveness_service
from utils.image_utils import bytes_to_bgr, ensure_min_size

from schemas.auth_schema import (
    ActiveChallengeStartResponse,
    ActiveLivenessResponse,
    LivenessBurstResponse,
    LivenessResponse,
)

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/liveness", tags=["liveness"])
settings = get_settings()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _validate_verify_token(authorization: str | None) -> int:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer verify_token from /verify-face.",
        )
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_VERIFY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verify token.",
        )
    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    return int(uid)


def _active_instruction(action: str) -> str:
    if action == "turn_left":
        return "Turn your head slightly LEFT and capture."
    if action == "turn_right":
        return "Turn your head slightly RIGHT and capture."
    return "Follow active liveness challenge."


@router.post("/check-liveness", response_model=LivenessResponse)
async def check_liveness(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> LivenessResponse:
    """
    Requires `Authorization: Bearer <verify_token>` from /verify-face.
    Returns liveness score and a short-lived liveness_token if pass.
    """
    uid = _validate_verify_token(authorization)

    if not liveness_service.is_liveness_available() and not liveness_service.should_use_dev_fallback():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Liveness model not loaded. Place ONNX weights (see README).",
        )

    try:
        raw = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read upload.",
        ) from exc

    bgr = bytes_to_bgr(raw)
    if bgr is None or not ensure_min_size(bgr):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or too small image.",
        )

    score, err = liveness_service.predict_liveness_score(bgr)
    if score is None:
        LOGGER.error("Liveness inference error: %s", err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=err or "Liveness inference failed.",
        )

    live = score >= settings.LIVENESS_SCORE_THRESHOLD
    liveness_token = None
    if live:
        liveness_token = auth_service.create_liveness_token(int(uid))

    return LivenessResponse(
        live=live,
        score=float(score),
        liveness_token=liveness_token,
        message="Liveness passed." if live else "Liveness check failed (possible spoof).",
    )


@router.post("/check-liveness-burst", response_model=LivenessBurstResponse)
async def check_liveness_burst(
    files: list[UploadFile] = File(...),
    authorization: str | None = Header(default=None),
) -> LivenessBurstResponse:
    """
    Stronger liveness endpoint that aggregates a burst of frames.
    Requires `Authorization: Bearer <verify_token>` from /verify-face.
    """
    uid = _validate_verify_token(authorization)

    if not liveness_service.is_liveness_available() and not liveness_service.should_use_dev_fallback():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Liveness model not loaded. Place ONNX weights (see README).",
        )

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No frames uploaded.")

    usable_files = files[: settings.LIVENESS_BURST_MAX_FRAMES]
    frame_scores: list[float] = []
    for file in usable_files:
        try:
            raw = await file.read()
        except Exception:
            continue
        bgr = bytes_to_bgr(raw)
        if bgr is None or not ensure_min_size(bgr):
            continue
        score, err = liveness_service.predict_liveness_score(bgr)
        if score is None:
            LOGGER.warning("Skipping frame due to liveness inference error: %s", err)
            continue
        frame_scores.append(float(score))

    if len(frame_scores) < settings.LIVENESS_BURST_MIN_FRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Need at least {settings.LIVENESS_BURST_MIN_FRAMES} valid frames; "
                f"received {len(frame_scores)}."
            ),
        )

    passed_frames = [s for s in frame_scores if s >= settings.LIVENESS_SCORE_THRESHOLD]
    pass_ratio = float(len(passed_frames) / len(frame_scores))
    aggregate_score = float(sum(frame_scores) / len(frame_scores))
    live = pass_ratio >= settings.LIVENESS_BURST_PASS_RATIO

    liveness_token = auth_service.create_liveness_token(uid) if live else None
    return LivenessBurstResponse(
        live=live,
        aggregate_score=aggregate_score,
        pass_ratio=pass_ratio,
        used_frames=len(frame_scores),
        frame_scores=frame_scores,
        liveness_token=liveness_token,
        message=(
            "Burst liveness passed."
            if live
            else "Burst liveness failed (possible spoof or unstable frames)."
        ),
    )


@router.post("/active-challenge/start", response_model=ActiveChallengeStartResponse)
def start_active_challenge(authorization: str | None = Header(default=None)) -> ActiveChallengeStartResponse:
    uid = _validate_verify_token(authorization)
    action = secrets.choice(["turn_left", "turn_right"])
    challenge_token = auth_service.create_active_challenge_token(uid, action)
    return ActiveChallengeStartResponse(
        challenge_token=challenge_token,
        action=action,
        instruction=_active_instruction(action),
    )


@router.post("/active-challenge/verify", response_model=ActiveLivenessResponse)
async def verify_active_challenge(
    challenge_token: str = Form(...),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> ActiveLivenessResponse:
    uid = _validate_verify_token(authorization)
    payload = auth_service.safe_decode(challenge_token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_ACTIVE_CHALLENGE):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired challenge token.")
    if int(payload.get("uid", -1)) != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Challenge token does not match user.")
    action = str(payload.get("action", "")).strip().lower()
    if action not in {"turn_left", "turn_right"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid challenge action.")

    raw = await file.read()
    bgr = bytes_to_bgr(raw)
    if bgr is None or not ensure_min_size(bgr):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or too small image.")

    landmarks = face_service.detect_primary_face_landmarks_bgr(bgr)
    if not landmarks:
        return ActiveLivenessResponse(
            live=False,
            action=action,
            yaw_score=0.0,
            message="No face landmarks detected. Keep face centered and retry.",
        )

    left_eye = landmarks["left_eye"]
    right_eye = landmarks["right_eye"]
    nose = landmarks["nose"]
    eye_center_x = float((left_eye[0] + right_eye[0]) * 0.5)
    eye_dist = float(abs(right_eye[0] - left_eye[0]) + 1e-6)
    yaw_score = float((nose[0] - eye_center_x) / eye_dist)

    threshold = float(settings.ACTIVE_LIVENESS_YAW_THRESHOLD)
    if action == "turn_left":
        passed = yaw_score <= -threshold
    else:
        passed = yaw_score >= threshold

    token = auth_service.create_liveness_token(uid) if passed else None
    return ActiveLivenessResponse(
        live=passed,
        action=action,
        yaw_score=yaw_score,
        liveness_token=token,
        message="Active liveness passed." if passed else "Active challenge not satisfied. Turn more and retry.",
    )
