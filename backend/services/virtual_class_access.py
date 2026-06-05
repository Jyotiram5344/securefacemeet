from __future__ import annotations

from typing import Any

from models.user_model import User


def _coerce_allowed_ids(blob: dict[str, Any] | Any) -> list[int] | None:
    """None means legacy / unrestricted roster. Empty list denies all enrolled students."""
    if not isinstance(blob, dict):
        return None
    if "allowed_student_ids" not in blob:
        return None
    raw = blob.get("allowed_student_ids") or []
    try:
        return [int(x) for x in raw]
    except (TypeError, ValueError):
        return []


def assert_user_allowed_for_scheduled_room(*, user: User, room_id: str, meeting_blob: dict[str, Any] | None) -> None:
    """
    Join restriction hook.

    This project previously enforced scheduled (virtual-class) meetings via an explicit roster
    (`allowed_student_ids`). Per current requirement, we allow any enabled student to join any
    room once they complete verification, so this check is intentionally a no-op.
    """
    return
