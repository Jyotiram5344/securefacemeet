"""User model — stores ArcFace 512-D embedding as JSON array (floats)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Student / staff identifier shown in admin and virtual class rosters (unique when set).
    student_external_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="student", index=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Relative path under FACE_IMAGES_DIR e.g. faces/123.jpg
    face_image_relpath: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Cohort / section for roster filtering (aligned with Virtual Class audience tags, e.g. A, B, CSE-A).
    student_class: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Optional password for future account flows; face auth is primary for meeting gate
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # JSON string: list of 512 floats (normalized ArcFace embedding)
    face_embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
