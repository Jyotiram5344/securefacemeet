from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str

    model_config = {"from_attributes": True}


class RegisterFaceResponse(BaseModel):
    success: bool
    message: str
    user_id: int | None = None


class VerifyFaceResponse(BaseModel):
    verified: bool
    user_id: int | None = None
    email: str | None = None
    full_name: str | None = None
    student_class: str | None = None
    similarity: float | None = None
    verify_token: str | None = None
    message: str = ""
