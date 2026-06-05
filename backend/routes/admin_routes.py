"""Admin dashboard API — single shared admin account from environment."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.meeting_session_model import MeetingAttendanceLog
from models.user_model import User
from schemas.admin_schema import (
    AdminBulkStatusRequest,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserPatch,
    AdminUserRow,
    ParticipantAttendanceOut,
)
from services import auth_service, participant_export

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def require_admin(authorization: str | None) -> dict:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer admin token.")
    payload = auth_service.safe_decode(token)
    if not payload or not auth_service.require_token_type(payload, auth_service.TOKEN_ADMIN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")
    return payload


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest) -> AdminLoginResponse:
    if body.username.strip() != settings.ADMIN_USERNAME or body.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials.")
    token = auth_service.create_admin_session_token(settings.ADMIN_USERNAME)
    return AdminLoginResponse(access_token=token, expires_in=settings.JWT_ADMIN_EXPIRE_MINUTES * 60)


@router.get("/users", response_model=list[AdminUserRow])
def list_users(
    q: str | None = None,
    role: str | None = None,
    student_class: str | None = None,
    enabled: bool | None = None,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[AdminUserRow]:
    require_admin(authorization)
    query = db.query(User)
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                User.email.ilike(needle),
                User.full_name.ilike(needle),
                User.student_external_id.ilike(needle),
            )
        )
    if role:
        query = query.filter(User.role == role.strip())
    if student_class:
        normalized = student_class.strip().upper()
        if normalized:
            query = query.filter(User.student_class == normalized)
    if enabled is not None:
        query = query.filter(User.is_enabled == enabled)
    rows = query.order_by(User.id.asc()).all()
    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            student_external_id=u.student_external_id,
            student_class=u.student_class,
            role=u.role,
            is_enabled=bool(u.is_enabled),
            has_face_image=bool(u.face_image_relpath),
        )
        for u in rows
    ]


@router.get("/users/{user_id}/face")
def get_user_face(
    user_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    require_admin(authorization)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.face_image_relpath:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Face image not found.")
    base = Path(settings.FACE_IMAGES_DIR).expanduser()
    base_resolved = base.resolve()
    path = (base / user.face_image_relpath).resolve()
    try:
        path.relative_to(base_resolved)
    except ValueError as exc:
        LOGGER.warning("Path traversal attempt blocked for user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stored path.") from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image missing on disk.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/meta/student-classes", response_model=list[str])
def list_distinct_student_classes(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[str]:
    require_admin(authorization)
    rows = (
        db.query(User.student_class)
        .filter(User.student_class.is_not(None))
        .filter(User.student_class != "")
        .distinct()
        .order_by(User.student_class.asc())
        .all()
    )
    return sorted({str(r[0]).strip().upper() for r in rows if r[0]})


@router.post("/users/bulk-status")
def bulk_set_user_status(
    body: AdminBulkStatusRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    require_admin(authorization)
    ids = sorted(set(body.user_ids))
    users = db.query(User).filter(User.id.in_(ids)).all()
    found_ids = {u.id for u in users}
    missing = sorted(set(ids) - found_ids)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown user_ids: {missing}",
        )
    for user in users:
        user.is_enabled = bool(body.is_enabled)
        db.add(user)
    db.commit()
    return {"updated": len(users), "is_enabled": bool(body.is_enabled)}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    require_admin(authorization)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.face_image_relpath:
        base = Path(settings.FACE_IMAGES_DIR).expanduser()
        base_resolved = base.resolve()
        path = (base / user.face_image_relpath).resolve()
        try:
            if path.is_file():
                path.relative_to(base_resolved)
                path.unlink(missing_ok=True)
        except ValueError:
            LOGGER.warning("Skipped deleting face outside storage root for user_id=%s", user_id)
        except OSError:
            LOGGER.warning("Could not delete face file for user_id=%s", user_id)
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/users/{user_id}", response_model=AdminUserRow)
def patch_user(
    user_id: int,
    body: AdminUserPatch,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AdminUserRow:
    require_admin(authorization)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    incoming = body.model_dump(exclude_unset=True)
    if "is_enabled" in incoming:
        user.is_enabled = bool(body.is_enabled)
    if "role" in incoming and body.role is not None:
        user.role = body.role
    if "student_class" in incoming:
        label = (body.student_class or "").strip().upper()
        user.student_class = label or None
    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminUserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        student_external_id=user.student_external_id,
        student_class=user.student_class,
        role=user.role,
        is_enabled=bool(user.is_enabled),
        has_face_image=bool(user.face_image_relpath),
    )


def _participant_logs_query(
    db: Session,
    room_id: str,
    filter_mode: Literal["qualified", "dwell_only", "all"],
):
    rid = room_id.strip()
    q = db.query(MeetingAttendanceLog).filter(MeetingAttendanceLog.meeting_id == rid)
    if filter_mode == "qualified":
        q = q.filter(MeetingAttendanceLog.status == "valid")
    elif filter_mode == "dwell_only":
        q = q.filter(MeetingAttendanceLog.meets_dwell_threshold.is_(True))
    return q.order_by(MeetingAttendanceLog.exit_time.desc())


def _logs_to_export_dicts(db: Session, logs: list[MeetingAttendanceLog]) -> list[dict]:
    rows: list[dict] = []
    for log in logs:
        try:
            uid = int(log.user_id)
        except ValueError:
            uid = -1
        user = db.get(User, uid) if uid >= 0 else None
        dr = float(log.dwell_ratio or 0.0)
        dwell_pct = round(dr * 100.0, 2)
        fully = log.status == "valid"
        join_s = log.join_time.isoformat() if log.join_time else ""
        exit_s = log.exit_time.isoformat() if log.exit_time else ""
        rows.append(
            {
                "meeting_id": log.meeting_id,
                "log_id": log.id,
                "user_id": uid,
                "full_name": user.full_name if user else "(deleted)",
                "email": user.email if user else "",
                "student_external_id": user.student_external_id if user else None,
                "student_class": user.student_class if user else None,
                "join_time": join_s,
                "exit_time": exit_s,
                "seconds_present": float(log.seconds_present or 0.0),
                "scheduled_duration_seconds": float(log.scheduled_duration_seconds or 0.0),
                "dwell_ratio": dr,
                "dwell_percent": dwell_pct,
                "meets_dwell_threshold": bool(log.meets_dwell_threshold),
                "meets_face_threshold": bool(log.meets_face_threshold),
                "status": log.status,
                "fully_qualified": fully,
            }
        )
    return rows


@router.get("/participants/room/{room_id}", response_model=list[ParticipantAttendanceOut])
def list_room_participants(
    room_id: str,
    filter_mode: Literal["qualified", "dwell_only", "all"] = Query(default="qualified"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[ParticipantAttendanceOut]:
    require_admin(authorization)
    logs = _participant_logs_query(db, room_id, filter_mode).all()
    return [ParticipantAttendanceOut.model_validate(r) for r in _logs_to_export_dicts(db, logs)]


@router.get("/participants/room/{room_id}/export")
def export_room_participants(
    room_id: str,
    fmt: Literal["csv", "xlsx", "pdf"] = Query(...),
    filter_mode: Literal["qualified", "dwell_only", "all"] = Query(default="qualified"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """Download participant attendance for one Jitsi / virtual-class room."""
    require_admin(authorization)
    logs = _participant_logs_query(db, room_id, filter_mode).all()
    plain = _logs_to_export_dicts(db, logs)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in room_id.strip())[:80] or "room"

    if fmt == "csv":
        data = participant_export.to_csv_bytes(plain)
        media = "text/csv; charset=utf-8"
        ext = "csv"
    elif fmt == "xlsx":
        data = participant_export.to_xlsx_bytes(plain)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        data = participant_export.to_pdf_bytes(plain, f"Participants — {room_id.strip()} — filter={filter_mode}")
        media = "application/pdf"
        ext = "pdf"

    ascii_name = f"participants_{safe_name}_{filter_mode}.{ext}"
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(ascii_name)}"
    return StreamingResponse(
        iter([data]),
        media_type=media,
        headers={"Content-Disposition": disp},
    )
