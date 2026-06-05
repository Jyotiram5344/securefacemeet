from __future__ import annotations

from pydantic import BaseModel, Field


class MonitorVerifyRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    meeting_id: str = Field(..., min_length=1, max_length=256)
    frame: str = Field(..., min_length=50, description="Base64-encoded image string")
    challenge_action: str | None = Field(default=None, description="turn_left | turn_right | smile")


class PeriodicVerifyResponse(BaseModel):
    success: bool
    similarity_score: float
    attendance_penalty: int
    warning_count: int
    attendance_score: int
    consecutive_failures: int = 0
    recommends_removal: bool = False
    face_count: int | None = None


class RandomVerifyResponse(BaseModel):
    success: bool
    action_detected: str
    attendance_penalty: int
    warning_count: int
    attendance_score: int
