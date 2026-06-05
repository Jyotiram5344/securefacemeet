"""Meeting JWT issuance and gated meeting info."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user_model import User
from schemas.auth_schema import (
    MeetingSessionBindRequest,
    MeetingSessionLeaveRequest,
    MeetingTokenRequest,
    MeetingTokenResponse,
)
from services import auth_service, virtual_class_store as vc_store
from services.meeting_participation_service import assert_can_issue_token_for_room, join_meeting, leave_meeting
from services.virtual_class_access import assert_user_allowed_for_scheduled_room

router = APIRouter(prefix="/meeting", tags=["meeting"])
settings = get_settings()
LOGGER = logging.getLogger(__name__)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.post("/generate-meeting-token", response_model=MeetingTokenResponse)
def generate_meeting_token(
    body: MeetingTokenRequest | None = Body(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MeetingTokenResponse:
    """
    Exchange liveness_token for a 5-minute meeting access JWT.
    Requires `Authorization: Bearer <liveness_token>`.
    """
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer liveness_token.",
        )
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_LIVENESS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired liveness token.",
        )
    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    user = db.query(User).filter(User.id == int(uid)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User record missing.")
    if not bool(user.is_enabled):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled. Ask an administrator to re-enable it.",
        )

    room_id = (body.room_id.strip() if body and body.room_id else None) or None
    meetings = vc_store.load_meetings()

    scheduled = meetings.get(room_id) if room_id else None
    try:
        if room_id:
            assert_user_allowed_for_scheduled_room(user=user, room_id=room_id, meeting_blob=scheduled if scheduled else None)
        assert_can_issue_token_for_room(db, user_id=str(int(uid)), desired_meeting_id=room_id)
    except ValueError as exc:
        LOGGER.info("Meeting token denied for uid=%s: %s", uid, exc)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    meeting_jwt = auth_service.create_meeting_token(
        int(uid),
        room_id=room_id,
        full_name=user.full_name,
        email=user.email,
    )
    expires_in = settings.JWT_MEETING_EXPIRE_MINUTES * 60
    return MeetingTokenResponse(access_token=meeting_jwt, expires_in=expires_in)


@router.post("/session/join")
def join_session(
    body: MeetingSessionBindRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer meeting token.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_MEETING):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid meeting token.")
    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    meeting_id = body.meeting_id.strip()
    jwt_room = payload.get("room_id")
    if jwt_room and jwt_room.strip() != meeting_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Meeting token is bound to a different room.")

    user = db.query(User).filter(User.id == int(uid)).first()
    if user is None or not bool(user.is_enabled):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not permitted.")

    meetings = vc_store.load_meetings()
    scheduled = meetings.get(meeting_id)
    try:
        assert_user_allowed_for_scheduled_room(user=user, room_id=meeting_id, meeting_blob=scheduled if scheduled else None)
        join_meeting(db, user_id=str(int(uid)), meeting_id=meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    return {"joined": True, "meeting_id": meeting_id}


@router.post("/session/leave")
def leave_session(
    body: MeetingSessionLeaveRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer meeting token.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_MEETING):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid meeting token.")
    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")

    meeting_id = body.meeting_id.strip()
    jwt_room = payload.get("room_id")
    if jwt_room and jwt_room.strip() != meeting_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Meeting token is bound to a different room.")

    leave_meeting(db, user_id=str(int(uid)), removed=bool(body.removed))
    db.commit()
    return {"left": True}


@router.get("/verify-token")
def verify_meeting_token(authorization: str | None = Header(default=None)) -> dict:
    """Validate meeting JWT (for frontend / gateway checks)."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_MEETING):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid meeting token.")
    return {"valid": True, "user_id": payload.get("uid"), "room_id": payload.get("room_id")}
