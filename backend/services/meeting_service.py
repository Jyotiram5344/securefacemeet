"""Meeting room helpers — optional DB-backed rooms."""
from __future__ import annotations

import secrets
import string

from sqlalchemy.orm import Session

from models.meeting_model import Meeting


def generate_room_id(length: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_meeting(
    db: Session,
    title: str,
    host_user_id: int | None,
    room_id: str | None = None,
) -> Meeting:
    rid = room_id or generate_room_id()
    m = Meeting(room_id=rid, title=title, host_user_id=host_user_id)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def get_meeting_by_room(db: Session, room_id: str) -> Meeting | None:
    return db.query(Meeting).filter(Meeting.room_id == room_id).first()
