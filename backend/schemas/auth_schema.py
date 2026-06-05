from __future__ import annotations

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """Decoded JWT claims (subset)."""

    sub: str | None = None
    typ: str | None = None
    uid: int | None = None


class MeetingTokenRequest(BaseModel):
    """Optional room hint for meeting JWT claims."""

    room_id: str | None = Field(default=None, max_length=256)


class MeetingSessionBindRequest(BaseModel):
    meeting_id: str = Field(..., max_length=256)


class MeetingSessionLeaveRequest(BaseModel):
    meeting_id: str = Field(..., max_length=256)
    removed: bool = False


class MeetingTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until expiry")


class LivenessResponse(BaseModel):
    live: bool
    score: float
    liveness_token: str | None = None
    message: str = ""


class LivenessBurstResponse(BaseModel):
    live: bool
    aggregate_score: float
    pass_ratio: float
    used_frames: int
    frame_scores: list[float] = Field(default_factory=list)
    liveness_token: str | None = None
    message: str = ""


class ActiveChallengeStartResponse(BaseModel):
    challenge_token: str
    action: str
    instruction: str


class ActiveLivenessResponse(BaseModel):
    live: bool
    action: str
    yaw_score: float
    liveness_token: str | None = None
    message: str = ""
