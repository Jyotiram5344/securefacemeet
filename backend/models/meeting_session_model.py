"""Active participation and finalized attendance logs for meetings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ActiveMeetingParticipation(Base):
    """At most one open meeting per registered user."""

    __tablename__ = "active_meeting_participation"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    join_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cumulative_verified_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MeetingAttendanceLog(Base):
    """Final attendance row when a participant leaves / is kicked."""

    __tablename__ = "meeting_attendance_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    meeting_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    join_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # valid | removed | incomplete
    seconds_present: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scheduled_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dwell_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    meets_dwell_threshold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meets_face_threshold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
