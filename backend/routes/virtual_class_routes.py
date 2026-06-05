"""Virtual class sessions (Jitsi room scheduling) aligned with legacy app2 Streamlit flow."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user_model import User
from schemas.virtual_class_schema import (
    AttendanceSnapshotResponse,
    CreateVirtualSessionRequest,
    CreateVirtualSessionResponse,
    TeacherMeetingPatchRequest,
    TeacherMeetingSummary,
    VirtualSessionStatusResponse,
)
from services import auth_service, face_service, monitoring_service
from services.virtual_class_access import assert_user_allowed_for_scheduled_room
from services import virtual_class_store as vc_store
from utils.image_utils import bytes_to_bgr, ensure_min_size

router = APIRouter(prefix="/virtual-class", tags=["virtual-class"])
settings = get_settings()


def _require_teacher_key(x_teacher_key: str | None) -> None:
    expected = (settings.TEACHER_API_KEY or "").strip()
    if not expected:
        return
    if not x_teacher_key or x_teacher_key.strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid teacher credential.")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.post("/sessions", response_model=CreateVirtualSessionResponse)
def create_session(
    body: CreateVirtualSessionRequest,
    x_teacher_key: str | None = Header(default=None, alias="X-Teacher-Key"),
    db: Session = Depends(get_db),
) -> CreateVirtualSessionResponse:
    _require_teacher_key(x_teacher_key)
    subject = body.subject.strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject is required.")

    roster = sorted(set(int(uid) for uid in body.allowed_student_ids))
    if len(roster) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one approved student.",
        )

    roster_users = db.query(User).filter(User.id.in_(roster)).all()
    if len(roster_users) != len(roster):
        missing = sorted(set(roster) - {u.id for u in roster_users})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown user IDs in roster: {missing}",
        )
    inactive = [u.id for u in roster_users if not bool(u.is_enabled)]
    if inactive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot roster disabled accounts: {inactive}",
        )

    room_id = f"{subject}_{body.class_filter}_{int(time.time())}".replace(" ", "_")
    start_t = time.time()
    end_t = start_t + (body.duration_minutes * 60.0)
    meetings = vc_store.load_meetings()
    meetings[room_id] = {
        "subject": subject,
        "class": body.class_filter,
        "duration": body.duration_minutes,
        "start_time": start_t,
        "end_time": end_t,
        "allowed_student_ids": roster,
    }
    vc_store.save_meetings(meetings)
    return CreateVirtualSessionResponse(
        room_id=room_id,
        subject=subject,
        class_filter=body.class_filter,
        duration_minutes=body.duration_minutes,
        start_time=start_t,
        end_time=end_t,
        allowed_student_ids=roster,
    )


@router.get("/sessions/{room_id}", response_model=VirtualSessionStatusResponse)
def get_session_status(room_id: str) -> VirtualSessionStatusResponse:
    meetings = vc_store.load_meetings()
    if room_id not in meetings:
        return VirtualSessionStatusResponse(
            found=False,
            room_id=room_id,
            meeting_closed=True,
        )
    m = meetings[room_id]
    end_t = float(m["end_time"])
    now = time.time()
    ml = vc_store.minutes_left(end_t, now)
    # Consider the meeting "closed" exactly at configured end_time.
    # (The attendance snapshot endpoint still uses attendance_window_open grace rules.)
    closed = ml <= 0.0
    return VirtualSessionStatusResponse(
        found=True,
        room_id=room_id,
        subject=str(m.get("subject", "")),
        class_filter=str(m.get("class", "")),
        minutes_left=round(ml, 2),
        attendance_window_open=vc_store.attendance_window_open(end_t, now),
        meeting_closed=closed,
    )


@router.post("/sessions/{room_id}/attendance-snapshot", response_model=AttendanceSnapshotResponse)
async def attendance_snapshot(
    room_id: str,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AttendanceSnapshotResponse:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer meeting token.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_MEETING):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid meeting token.")
    jwt_room = payload.get("room_id")
    if jwt_room and jwt_room != room_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Meeting token is bound to a different room.",
        )

    meetings = vc_store.load_meetings()
    if room_id not in meetings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")
    m = meetings[room_id]
    end_t = float(m["end_time"])
    if not vc_store.attendance_window_open(end_t):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attendance is only available in the last 15 minutes of the session (with a short grace period).",
        )

    uid = payload.get("uid")
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    user = db.query(User).filter(User.id == int(uid)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not bool(user.is_enabled):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled.")

    try:
        assert_user_allowed_for_scheduled_room(user=user, room_id=room_id, meeting_blob=m)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        raw = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read upload.") from exc

    bgr = bytes_to_bgr(raw)
    if bgr is None or not ensure_min_size(bgr):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or too small image.")

    fc = face_service.count_faces_bgr(bgr)
    if fc == 0 or fc is None or fc > 1:
        message = (
            "No face detected." if fc == 0 else "Multiple faces in frame." if fc and fc > 1 else "Unable to analyse frame lighting."
        )
        state = monitoring_service.get_or_create_attendance_state(db, str(uid), room_id)
        monitoring_service.apply_penalty(state, settings.PERIODIC_FAIL_PENALTY)
        monitoring_service.log_presence_event(
            db,
            user_id=str(uid),
            meeting_id=room_id,
            verification_type="virtual_class_attendance",
            passed=False,
            similarity_score=None,
        )
        db.commit()
        return AttendanceSnapshotResponse(marked=False, similarity_score=None, message=message)

    try:
        probe = await asyncio.wait_for(
            asyncio.to_thread(face_service.extract_embedding_bgr, bgr),
            timeout=settings.MONITOR_VERIFY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Face processing timed out.") from exc

    if probe is None:
        state = monitoring_service.get_or_create_attendance_state(db, str(uid), room_id)
        monitoring_service.log_presence_event(
            db,
            user_id=str(uid),
            meeting_id=room_id,
            verification_type="virtual_class_attendance",
            passed=False,
            similarity_score=None,
        )
        db.commit()
        return AttendanceSnapshotResponse(marked=False, similarity_score=None, message="No face detected.")

    ref = face_service.json_to_embedding(user.face_embedding_json)
    similarity = float(face_service.cosine_similarity(probe, ref))
    success = similarity >= settings.FACE_MATCH_THRESHOLD

    state = monitoring_service.get_or_create_attendance_state(db, str(uid), room_id)
    penalty = 0 if success else settings.PERIODIC_FAIL_PENALTY
    monitoring_service.apply_penalty(state, penalty)
    monitoring_service.log_presence_event(
        db,
        user_id=str(uid),
        meeting_id=room_id,
        verification_type="virtual_class_attendance",
        passed=success,
        similarity_score=similarity,
    )
    db.commit()

    return AttendanceSnapshotResponse(
        marked=success,
        similarity_score=similarity,
        message="Attendance recorded." if success else "Face does not match enrolled identity.",
    )


def _serialize_teacher_summary(room_id: str, blob: dict) -> TeacherMeetingSummary:
    allowed = blob.get("allowed_student_ids")
    roster: list[int]
    if allowed is None:
        roster = []
    else:
        roster = sorted({int(x) for x in allowed})
    return TeacherMeetingSummary(
        room_id=room_id,
        subject=str(blob.get("subject", "")),
        class_filter=str(blob.get("class", "")),
        duration_minutes=float(blob.get("duration", 0)),
        start_time=float(blob.get("start_time", 0.0)),
        end_time=float(blob.get("end_time", 0.0)),
        allowed_student_ids=roster,
    )


@router.get("/teacher/students", response_model=list[dict])
def list_students_for_roster(
    x_teacher_key: str | None = Header(default=None, alias="X-Teacher-Key"),
    db: Session = Depends(get_db),
):
    _require_teacher_key(x_teacher_key)
    rows = (
        db.query(User)
        .filter(User.is_enabled.is_(True))
        .filter(User.role.in_(["student"]))
        .order_by(User.full_name.asc())
        .all()
    )
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "student_external_id": u.student_external_id,
            "student_class": u.student_class,
            "role": u.role,
        }
        for u in rows
    ]


@router.get("/teacher/meetings", response_model=list[TeacherMeetingSummary])
def teacher_list_meetings(x_teacher_key: str | None = Header(default=None, alias="X-Teacher-Key")):
    _require_teacher_key(x_teacher_key)
    meetings = vc_store.load_meetings()
    return [_serialize_teacher_summary(room_id, blob) for room_id, blob in sorted(meetings.items(), key=lambda item: item[0])]


@router.patch("/teacher/meetings/{room_id}", response_model=TeacherMeetingSummary)
def teacher_patch_meeting(
    room_id: str,
    body: TeacherMeetingPatchRequest,
    x_teacher_key: str | None = Header(default=None, alias="X-Teacher-Key"),
    db: Session = Depends(get_db),
) -> TeacherMeetingSummary:
    _require_teacher_key(x_teacher_key)
    meetings = vc_store.load_meetings()
    if room_id not in meetings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found.")
    roster = sorted(set(int(uid) for uid in body.allowed_student_ids))
    if len(roster) < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one student.")
    roster_users = db.query(User).filter(User.id.in_(roster)).all()
    if len(roster_users) != len(roster):
        missing = sorted(set(roster) - {u.id for u in roster_users})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown user IDs: {missing}")
    inactive = [u.id for u in roster_users if not bool(u.is_enabled)]
    if inactive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Disabled accounts blocked: {inactive}")

    blob = meetings[room_id]
    blob["allowed_student_ids"] = roster
    vc_store.save_meetings(meetings)
    return _serialize_teacher_summary(room_id, blob)


@router.delete("/teacher/meetings/{room_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def teacher_delete_meeting(
    room_id: str,
    x_teacher_key: str | None = Header(default=None, alias="X-Teacher-Key"),
) -> Response:
    _require_teacher_key(x_teacher_key)
    meetings = vc_store.load_meetings()
    if room_id not in meetings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found.")
    meetings.pop(room_id, None)
    vc_store.save_meetings(meetings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
