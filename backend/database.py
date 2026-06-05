"""SQLAlchemy engine, session factory, and declarative base."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_kwargs = {"future": True}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_existing_columns(connection, table: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {str(r[1]) for r in rows}


def _run_sqlite_migrations() -> None:
    """Lightweight ALTERs for SQLite when models gain columns (cannot rely on CREATE TABLE only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        existing = _sqlite_existing_columns(conn, "users")
        alterations: list[tuple[str, str]] = []
        if "student_external_id" not in existing:
            alterations.append(("student_external_id", "ALTER TABLE users ADD COLUMN student_external_id VARCHAR(128)"))
        if "role" not in existing:
            alterations.append(("role", "ALTER TABLE users ADD COLUMN role VARCHAR(32) DEFAULT 'student'"))
        if "is_enabled" not in existing:
            alterations.append(("is_enabled", "ALTER TABLE users ADD COLUMN is_enabled BOOLEAN DEFAULT 1"))
        if "face_image_relpath" not in existing:
            alterations.append(("face_image_relpath", "ALTER TABLE users ADD COLUMN face_image_relpath VARCHAR(512)"))
        if "student_class" not in existing:
            alterations.append(("student_class", "ALTER TABLE users ADD COLUMN student_class VARCHAR(64)"))
        for _name, ddl in alterations:
            conn.execute(text(ddl))
        if alterations:
            conn.commit()

        conn.execute(text("UPDATE users SET role='student' WHERE role IS NULL OR role = ''"))
        conn.execute(text("UPDATE users SET is_enabled=1 WHERE is_enabled IS NULL"))
        conn.commit()

        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_student_external_id "
                "ON users(student_external_id) WHERE student_external_id IS NOT NULL"
            )
        )
        conn.commit()

        log_existing = _sqlite_existing_columns(conn, "meeting_attendance_logs")
        log_alters: list[str] = []
        if "seconds_present" not in log_existing:
            log_alters.append("ALTER TABLE meeting_attendance_logs ADD COLUMN seconds_present FLOAT DEFAULT 0")
        if "scheduled_duration_seconds" not in log_existing:
            log_alters.append("ALTER TABLE meeting_attendance_logs ADD COLUMN scheduled_duration_seconds FLOAT DEFAULT 0")
        if "dwell_ratio" not in log_existing:
            log_alters.append("ALTER TABLE meeting_attendance_logs ADD COLUMN dwell_ratio FLOAT DEFAULT 0")
        if "meets_dwell_threshold" not in log_existing:
            log_alters.append("ALTER TABLE meeting_attendance_logs ADD COLUMN meets_dwell_threshold BOOLEAN DEFAULT 0")
        if "meets_face_threshold" not in log_existing:
            log_alters.append("ALTER TABLE meeting_attendance_logs ADD COLUMN meets_face_threshold BOOLEAN DEFAULT 0")
        for ddl in log_alters:
            conn.execute(text(ddl))
        if log_alters:
            conn.commit()


def init_db() -> None:
    """Create tables if they do not exist."""
    import models.user_model  # noqa: F401
    import models.meeting_model  # noqa: F401
    import models.attendance_model  # noqa: F401
    import models.presence_log_model  # noqa: F401
    import models.meeting_session_model  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()
