from __future__ import annotations

from sqlalchemy.orm import Session

from models.attendance_model import AttendanceState
from models.presence_log_model import PresenceLog


def _compute_final_status(score: int, warnings: int) -> str:
    if score < 50 or warnings >= 5:
        return "critical"
    if score < 75 or warnings >= 3:
        return "warning"
    return "good"


def get_or_create_attendance_state(db: Session, user_id: str, meeting_id: str) -> AttendanceState:
    state = (
        db.query(AttendanceState)
        .filter(AttendanceState.user_id == user_id, AttendanceState.meeting_id == meeting_id)
        .first()
    )
    if state is not None:
        return state
    state = AttendanceState(
        user_id=user_id,
        meeting_id=meeting_id,
        attendance_score=100,
        warning_count=0,
        final_status="good",
    )
    db.add(state)
    db.flush()
    return state


def log_presence_event(
    db: Session,
    *,
    user_id: str,
    meeting_id: str,
    verification_type: str,
    passed: bool,
    similarity_score: float | None = None,
) -> None:
    db.add(
        PresenceLog(
            user_id=user_id,
            meeting_id=meeting_id,
            verification_type=verification_type,
            result="pass" if passed else "fail",
            similarity_score=similarity_score,
        )
    )


def apply_penalty(state: AttendanceState, penalty: int) -> None:
    if penalty <= 0:
        state.final_status = _compute_final_status(state.attendance_score, state.warning_count)
        return
    state.warning_count += 1
    state.attendance_score = max(0, int(state.attendance_score - penalty))
    state.final_status = _compute_final_status(state.attendance_score, state.warning_count)
