"""
Application configuration — load from environment (.env) for production.
HTTPS-ready: set CORS and trusted hosts in deployment.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "SecureFaceMeet API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./securefacemeet.db",
        description="SQLAlchemy URL for SQLite",
    )

    # JWT — use long random secret in production
    JWT_SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32",
        min_length=16,
    )
    JWT_ALGORITHM: str = "HS256"
    # Short-lived tokens in the verification chain
    JWT_VERIFY_EXPIRE_MINUTES: int = 2
    JWT_LIVENESS_EXPIRE_MINUTES: int = 2
    JWT_MEETING_EXPIRE_MINUTES: int = 240

    # Demo admin gate (plaintext password in env for local setups only).
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = Field(default="admin123", description="Rotate in production deployments.")
    JWT_ADMIN_EXPIRE_MINUTES: int = 120

    # Protects teacher virtual-class CRUD in absence of teacher accounts (lab default).
    TEACHER_API_KEY: str | None = Field(default="teacher-dev-key", description="Sent as X-Teacher-Key.")

    # Stored enrollment photos (JPEG) for admin preview.
    FACE_IMAGES_DIR: str = "./data/faces"

    # Attendance finalized as valid once cumulative uninterrupted verified time reaches this.
    ATTENDANCE_MIN_VERIFIED_SECONDS: float = 45.0
    # Share of scheduled virtual-class meeting length the participant must remain connected (0–1).
    ATTENDANCE_MIN_DWELL_RATIO: float = 0.9
    # Estimated seconds credited per passing periodic verification (frontend should match cadence).
    PERIODIC_VERIFIED_CREDIT_SECONDS: float = 8.0

    # Consecutive periodic failures (camera/identity) before recommending forced hangup client-side.
    LIVE_FACE_FAILS_BEFORE_REMOVAL: int = 3

    # Face recognition (InsightFace ArcFace)
    INSIGHTFACE_MODEL_NAME: str = "buffalo_l"
    INSIGHTFACE_ROOT: str = "~/.insightface"
    FACE_MATCH_THRESHOLD: float = 0.6
    FACE_EMBEDDING_DIM: int = 512

    # Passive liveness (Silent-Face-Anti-Spoof ONNX)
    # Place ONNX model path from https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
    ANTI_SPOOF_ONNX_PATH: str = "./weights/anti_spoof.onnx"
    LIVENESS_SCORE_THRESHOLD: float = 0.8
    # Some anti-spoof exports use class index 1 for "live".
    LIVENESS_LIVE_CLASS_INDEX: int = 0
    # index | one_minus_index | sum_except_index
    LIVENESS_SCORE_MODE: str = "index"
    LIVENESS_FACE_CROP_MARGIN: float = 0.15
    # Silent-Face typical preprocessing: BGR and (x - 127.5) / 128.
    LIVENESS_USE_RGB_INPUT: bool = False
    LIVENESS_INPUT_NORM: str = "silent_face"  # silent_face | zero_one
    LIVENESS_DEBUG_LOG_PROBS: bool = True
    # Dev-only bypass when ONNX is not available. Keep FALSE in production.
    DEV_ALLOW_LIVENESS_FALLBACK: bool = False
    # Burst-mode liveness aggregation settings.
    LIVENESS_BURST_MIN_FRAMES: int = 3
    LIVENESS_BURST_MAX_FRAMES: int = 10
    LIVENESS_BURST_PASS_RATIO: float = 0.6
    # Active liveness settings (head-turn challenge).
    ACTIVE_LIVENESS_EXPIRE_MINUTES: int = 2
    ACTIVE_LIVENESS_YAW_THRESHOLD: float = 0.08
    ACTIVE_LIVENESS_SMILE_RATIO_THRESHOLD: float = 0.44
    MONITOR_MAX_FRAME_BYTES: int = 2_500_000
    MONITOR_VERIFY_TIMEOUT_SECONDS: float = 3.0
    PERIODIC_SIMILARITY_THRESHOLD: float = 0.6
    PERIODIC_FAIL_PENALTY: int = 5
    RANDOM_FAIL_PENALTY: int = 10

    # Virtual class JSON store (scheduled Jitsi sessions)
    VIRTUAL_CLASS_DATA_DIR: str = "./data/virtual_class"

    # CORS (comma-separated in env: http://localhost:5173,https://app.example.com)
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
