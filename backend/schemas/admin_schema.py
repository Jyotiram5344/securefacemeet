from __future__ import annotations

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class AdminLoginResponse(BaseModel):
    access_token: str
    expires_in: int


class AdminUserRow(BaseModel):
    id: int
    email: str
    full_name: str
    student_external_id: str | None = None
    student_class: str | None = None
    role: str
    is_enabled: bool
    has_face_image: bool


class AdminUserPatch(BaseModel):
    is_enabled: bool | None = None
    role: str | None = Field(default=None, pattern="^(student|teacher|staff)$")
    student_class: str | None = Field(default=None, max_length=64)


class AdminBulkStatusRequest(BaseModel):
    user_ids: list[int] = Field(..., min_length=1, max_length=500)
    is_enabled: bool


class ParticipantAttendanceOut(BaseModel):
    log_id: int
    user_id: int
    full_name: str
    email: str
    student_external_id: str | None = None
    student_class: str | None = None
    meeting_id: str
    join_time: str
    exit_time: str
    seconds_present: float
    scheduled_duration_seconds: float
    dwell_ratio: float
    dwell_percent: float
    meets_dwell_threshold: bool
    meets_face_threshold: bool
    status: str
    fully_qualified: bool
