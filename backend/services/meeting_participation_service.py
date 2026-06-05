from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import get_settings
from models.meeting_session_model import ActiveMeetingParticipation, MeetingAttendanceLog
from services.virtual_class_store import load_meetings, scheduled_duration_seconds

settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """
    Normalize datetimes to timezone-aware UTC.
    SQLite and some DB drivers can return naive values even for timezone=True fields.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def active_for_user(db: Session, user_id: str) -> ActiveMeetingParticipation | None:
    return db.get(ActiveMeetingParticipation, user_id)


def _is_stale_participation(row: ActiveMeetingParticipation) -> bool:
    """
    Treat dangling active rows as stale when:
    - scheduled meeting already ended, or
    - unscheduled row has lived beyond meeting-token lifetime.
    """
    now = _utcnow()
    now_ts = now.timestamp()
    meetings = load_meetings()
    blob = meetings.get(row.meeting_id)
    if isinstance(blob, dict):
        try:
            end_t = float(blob.get("end_time", 0))
        except (TypeError, ValueError):
            end_t = 0.0
        if end_t > 0 and now_ts >= end_t:
            return True

    # Ad-hoc/unknown rooms: expire stale active marker after token lifetime.
    age_seconds = max(0.0, (now - _as_utc(row.join_time)).total_seconds())
    max_age_seconds = float(settings.JWT_MEETING_EXPIRE_MINUTES) * 60.0
    return age_seconds > max_age_seconds


def assert_can_issue_token_for_room(db: Session, *, user_id: str, desired_meeting_id: str | None) -> None:
    if not desired_meeting_id:
        return
    row = active_for_user(db, user_id)
    if row and row.meeting_id != desired_meeting_id.strip() and not _is_stale_participation(row):
        raise ValueError(f"Already active in meeting '{row.meeting_id}'. Finish that session before joining another.")


def join_meeting(db: Session, *, user_id: str, meeting_id: str) -> ActiveMeetingParticipation:
    row = active_for_user(db, user_id)
    if row and row.meeting_id != meeting_id:
        if _is_stale_participation(row):
            db.delete(row)
            db.flush()
            row = None
        else:
            raise ValueError(f"Already active in meeting '{row.meeting_id}'.")
    if row:
        return row
    participant = ActiveMeetingParticipation(user_id=user_id, meeting_id=meeting_id)
    db.add(participant)
    db.flush()
    return participant


def leave_meeting(db: Session, *, user_id: str, removed: bool) -> MeetingAttendanceLog | None:
    row = active_for_user(db, user_id)
    if row is None:
        return None
    join_time = _as_utc(row.join_time)
    meeting_id = row.meeting_id
    cumulative = float(row.cumulative_verified_seconds or 0.0)
    exit_time = _as_utc(_utcnow())

    present_secs_raw = max(0.0, (exit_time - join_time).total_seconds())
    sched_secs = float(scheduled_duration_seconds(meeting_id))

    if sched_secs > 0:
        dwell_ratio = min(1.0, present_secs_raw / sched_secs)
        meets_dwell = dwell_ratio >= float(settings.ATTENDANCE_MIN_DWELL_RATIO)
    else:
        # Ad-hoc Jitsi room (no virtual-class schedule): dwell rule not applicable.
        dwell_ratio = 1.0
        meets_dwell = True

    meets_face = cumulative >= float(settings.ATTENDANCE_MIN_VERIFIED_SECONDS)

    if removed:
        status = "removed"
    elif meets_dwell and meets_face:
        status = "valid"
    else:
        status = "incomplete"

    log = MeetingAttendanceLog(
        user_id=user_id,
        meeting_id=meeting_id,
        join_time=join_time,
        exit_time=exit_time,
        status=status,
        seconds_present=present_secs_raw,
        scheduled_duration_seconds=sched_secs,
        dwell_ratio=float(dwell_ratio),
        meets_dwell_threshold=bool(meets_dwell),
        meets_face_threshold=bool(meets_face),
    )
    db.delete(row)
    db.add(log)
    db.flush()
    return log


def ensure_participation_row(db: Session, *, user_id: str, meeting_id: str) -> ActiveMeetingParticipation:
    row = active_for_user(db, user_id)
    if row is None:
        row = ActiveMeetingParticipation(user_id=user_id, meeting_id=meeting_id)
        db.add(row)
        db.flush()
        return row
    if row.meeting_id != meeting_id:
        raise ValueError("Meeting id mismatch.")
    return row


def apply_verification_success(db: Session, *, user_id: str, meeting_id: str, credit_seconds: float) -> ActiveMeetingParticipation:
    row = ensure_participation_row(db, user_id=user_id, meeting_id=meeting_id)
    row.cumulative_verified_seconds = float(row.cumulative_verified_seconds or 0.0) + float(credit_seconds)
    row.consecutive_failures = 0
    db.add(row)
    db.flush()
    return row


def apply_verification_failure(db: Session, *, user_id: str, meeting_id: str) -> ActiveMeetingParticipation:
    """Identity failure resets the cumulative streak (must be uninterrupted)."""
    row = ensure_participation_row(db, user_id=user_id, meeting_id=meeting_id)
    row.consecutive_failures = int(row.consecutive_failures or 0) + 1
    row.cumulative_verified_seconds = 0.0
    db.add(row)
    db.flush()
    return row
