from __future__ import annotations

from pydantic import BaseModel, Field


class CreateVirtualSessionRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    class_filter: str = Field(..., pattern="^(A|B|Faculty)$")
    duration_minutes: float = Field(..., ge=1.0, le=240.0)
    allowed_student_ids: list[int] = Field(default_factory=list, description="Explicit roster of enrolled user IDs.")


class CreateVirtualSessionResponse(BaseModel):
    room_id: str
    subject: str
    class_filter: str
    duration_minutes: float
    start_time: float
    end_time: float
    allowed_student_ids: list[int] = Field(default_factory=list)


class TeacherMeetingSummary(BaseModel):
    room_id: str
    subject: str
    class_filter: str
    duration_minutes: float
    start_time: float
    end_time: float
    allowed_student_ids: list[int]


class TeacherMeetingPatchRequest(BaseModel):
    allowed_student_ids: list[int] = Field(..., description="Replacement roster")


class VirtualSessionStatusResponse(BaseModel):
    found: bool
    room_id: str
    subject: str | None = None
    class_filter: str | None = None
    minutes_left: float | None = None
    attendance_window_open: bool = False
    meeting_closed: bool = False


class AttendanceSnapshotResponse(BaseModel):
    marked: bool
    similarity_score: float | None = None
    message: str = ""
