from __future__ import annotations

import asyncio
import logging
import random

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user_model import User
from schemas.monitor_schema import MonitorVerifyRequest, PeriodicVerifyResponse, RandomVerifyResponse
from services import auth_service, face_service, liveness_service, monitoring_service
from services.meeting_participation_service import (
    apply_verification_failure,
    apply_verification_success,
)
from utils.image_utils import base64_to_bgr, ensure_min_size

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/monitor", tags=["monitor"])
settings = get_settings()


def _bearer_token_from_header(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _require_meeting_token(authorization: str | None, expected_user_id: str, meeting_id: str) -> dict:
    token = _bearer_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Meeting token required.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_MEETING):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid meeting token.")
    if str(payload.get("uid")) != str(expected_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token user mismatch.")
    jwt_room = payload.get("room_id")
    if jwt_room and str(jwt_room).strip() != meeting_id.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token scope mismatch.")
    return payload


def _get_face_geometry(frame_bgr):
    lm = face_service.detect_primary_face_landmarks_bgr(frame_bgr)
    if not lm:
        return None
    left_eye = lm["left_eye"]
    right_eye = lm["right_eye"]
    nose = lm["nose"]
    eye_center_x = float((left_eye[0] + right_eye[0]) * 0.5)
    eye_dist = float(abs(right_eye[0] - left_eye[0]) + 1e-6)
    yaw = float((nose[0] - eye_center_x) / eye_dist)
    smile_ratio = 0.0
    if "mouth_left" in lm and "mouth_right" in lm:
        mouth_width = float(abs(lm["mouth_right"][0] - lm["mouth_left"][0]))
        smile_ratio = mouth_width / eye_dist
    return {"yaw": yaw, "smile_ratio": smile_ratio}


def _detect_action(frame_bgr, action: str) -> bool:
    geom = _get_face_geometry(frame_bgr)
    if not geom:
        return False
    yaw = geom["yaw"]
    if action == "turn_left":
        return yaw <= -settings.ACTIVE_LIVENESS_YAW_THRESHOLD
    if action == "turn_right":
        return yaw >= settings.ACTIVE_LIVENESS_YAW_THRESHOLD
    if action == "smile":
        return geom["smile_ratio"] >= settings.ACTIVE_LIVENESS_SMILE_RATIO_THRESHOLD
    return False


@router.post("/verify-periodic", response_model=PeriodicVerifyResponse)
async def verify_periodic(
    body: MonitorVerifyRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> PeriodicVerifyResponse:
    _require_meeting_token(authorization, body.user_id, body.meeting_id)

    frame = base64_to_bgr(body.frame, max_bytes=settings.MONITOR_MAX_FRAME_BYTES)
    if frame is None or not ensure_min_size(frame):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid frame payload.")

    user = db.query(User).filter(User.id == int(body.user_id)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not bool(user.is_enabled):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Disabled users cannot verify.")

    faces = face_service.count_faces_bgr(frame)
    if faces is None:
        faces = -1

    similarity = 0.0
    success = False
    probe = None

    if faces <= 0:
        success = False
        similarity = 0.0
    elif faces > 1:
        success = False
        similarity = 0.0
    else:
        try:
            probe = await asyncio.wait_for(
                asyncio.to_thread(face_service.extract_embedding_bgr, frame),
                timeout=settings.MONITOR_VERIFY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Periodic verification timed out.") from exc

        if probe is None:
            success = False
            similarity = 0.0
        else:
            ref = face_service.json_to_embedding(user.face_embedding_json)
            similarity = float(face_service.cosine_similarity(probe, ref))
            success = similarity >= settings.PERIODIC_SIMILARITY_THRESHOLD

    participant_state = (
        apply_verification_success(
            db,
            user_id=body.user_id,
            meeting_id=body.meeting_id,
            credit_seconds=settings.PERIODIC_VERIFIED_CREDIT_SECONDS,
        )
        if success
        else apply_verification_failure(db, user_id=body.user_id, meeting_id=body.meeting_id)
    )

    state = monitoring_service.get_or_create_attendance_state(db, body.user_id, body.meeting_id)
    penalty = 0 if success else settings.PERIODIC_FAIL_PENALTY
    monitoring_service.apply_penalty(state, penalty)
    monitoring_service.log_presence_event(
        db,
        user_id=body.user_id,
        meeting_id=body.meeting_id,
        verification_type="periodic",
        passed=success,
        similarity_score=similarity,
    )
    db.commit()

    face_count_report = faces if faces >= 0 else None
    consec = int(participant_state.consecutive_failures or 0)

    return PeriodicVerifyResponse(
        success=success,
        similarity_score=similarity,
        attendance_penalty=penalty,
        warning_count=state.warning_count,
        attendance_score=state.attendance_score,
        consecutive_failures=consec,
        recommends_removal=bool(consec >= int(settings.LIVE_FACE_FAILS_BEFORE_REMOVAL)),
        face_count=face_count_report,
    )


@router.post("/verify-random", response_model=RandomVerifyResponse)
async def verify_random(body: MonitorVerifyRequest, db: Session = Depends(get_db)) -> RandomVerifyResponse:
    frame = base64_to_bgr(body.frame, max_bytes=settings.MONITOR_MAX_FRAME_BYTES)
    if frame is None or not ensure_min_size(frame):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid frame payload.")

    action = (body.challenge_action or random.choice(["turn_left", "turn_right", "smile"])).strip().lower()
    if action not in {"turn_left", "turn_right", "smile"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid challenge_action.")

    try:
        score, err = await asyncio.wait_for(
            asyncio.to_thread(liveness_service.predict_liveness_score, frame),
            timeout=settings.MONITOR_VERIFY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Random verification timed out.") from exc

    if score is None:
        LOGGER.warning("Random liveness score unavailable: %s", err)
        liveness_ok = False
    else:
        liveness_ok = score >= settings.LIVENESS_SCORE_THRESHOLD

    action_ok = _detect_action(frame, action)
    success = bool(liveness_ok and action_ok)

    state = monitoring_service.get_or_create_attendance_state(db, body.user_id, body.meeting_id)
    penalty = 0 if success else settings.RANDOM_FAIL_PENALTY
    monitoring_service.apply_penalty(state, penalty)
    monitoring_service.log_presence_event(
        db,
        user_id=body.user_id,
        meeting_id=body.meeting_id,
        verification_type="random",
        passed=success,
        similarity_score=float(score or 0.0),
    )
    db.commit()

    return RandomVerifyResponse(
        success=success,
        action_detected=action if action_ok else "none",
        attendance_penalty=penalty,
        warning_count=state.warning_count,
        attendance_score=state.attendance_score,
    )
