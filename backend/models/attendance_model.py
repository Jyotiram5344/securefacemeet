from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AttendanceState(Base):
    __tablename__ = "attendance_states"
    __table_args__ = (UniqueConstraint("user_id", "meeting_id", name="uq_attendance_user_meeting"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    meeting_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    attendance_score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_status: Mapped[str] = mapped_column(String(32), default="good", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
