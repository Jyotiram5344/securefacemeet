"""Face registration and verification endpoints."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user_model import User
from schemas.user_schema import RegisterFaceResponse, VerifyFaceResponse
from services import auth_service, face_service
from utils.image_utils import bytes_to_bgr, ensure_min_size

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/face", tags=["face"])
settings = get_settings()


def _normalize_class_label(value: str) -> str:
    return value.strip().upper()


def _persist_registration_face(user_id: int, bgr: object) -> str:
    base = Path(settings.FACE_IMAGES_DIR).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    rel_path = f"{user_id}.jpg"
    cv2.imwrite(str(base / rel_path), bgr)
    return rel_path


@router.post("/register-face", response_model=RegisterFaceResponse)
async def register_face(
    email: str = Form(...),
    full_name: str = Form(...),
    student_external_id: str = Form(..., description="Institution-facing student identifier"),
    student_class: str = Form(..., description="Cohort / class section for roster & policy"),
    password: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RegisterFaceResponse:
    """Register user and store ArcFace embedding from a frontal face image."""
    try:
        raw = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read upload.",
        ) from exc

    bgr = bytes_to_bgr(raw)
    if bgr is None or not ensure_min_size(bgr):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or too small image.",
        )

    face_count = await asyncio.to_thread(face_service.count_faces_bgr, bgr)
    if face_count is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to reliably count faces. Try again.",
        )
    if face_count == 0:
        return RegisterFaceResponse(
            success=False,
            message="No face detected. Use brighter lighting and fill the frame with a single person.",
            user_id=None,
        )
    if face_count > 1:
        return RegisterFaceResponse(
            success=False,
            message="Multiple faces detected. Only one person should be visible.",
            user_id=None,
        )

    try:
        emb = await asyncio.to_thread(face_service.extract_embedding_bgr, bgr)
    except face_service.FaceServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if emb is None:
        return RegisterFaceResponse(
            success=False,
            message="Unable to derive a biometric template.",
            user_id=None,
        )

    student_id_normalized = student_external_id.strip().upper()
    if not student_id_normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student / staff identifier is required.",
        )

    class_label = _normalize_class_label(student_class)
    if not class_label:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student class / section is required.",
        )

    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    ext_collision = db.query(User).filter(User.student_external_id == student_id_normalized).first()
    if ext_collision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That student ID already exists.",
        )

    password_hash = None
    if password:
        try:
            # Keep legacy pre-hash normalization for very long secrets.
            password_for_hash = password
            if len(password.encode("utf-8")) > 72:
                password_for_hash = "sha256$" + hashlib.sha256(password.encode("utf-8")).hexdigest()
            password_hash = auth_service.hash_password(password_for_hash)
        except Exception as exc:
            LOGGER.exception("Password hashing failed during registration.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid password format. Use a shorter password or try again.",
            ) from exc

    user = User(
        email=email.lower().strip(),
        full_name=full_name.strip(),
        student_external_id=student_id_normalized,
        student_class=class_label,
        password_hash=password_hash,
        face_embedding_json=face_service.embedding_to_json(emb),
    )
    db.add(user)
    db.flush()
    try:
        rel = _persist_registration_face(user.id, bgr)
    except Exception as exc:
        LOGGER.exception("Failed to persist enrolment portrait.")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save portrait file.",
        ) from exc

    user.face_image_relpath = rel
    db.add(user)
    db.commit()
    db.refresh(user)

    return RegisterFaceResponse(
        success=True,
        message="Face enrolled successfully.",
        user_id=user.id,
    )


@router.post("/verify-face", response_model=VerifyFaceResponse)
async def verify_face(
    file: UploadFile = File(...),
    email: str | None = Form(default=None),
    restrict_to_class: str | None = Form(default=None, description="If set, enrolment class must match (case-insensitive)."),
    db: Session = Depends(get_db),
) -> VerifyFaceResponse:
    """
    Verify identity against stored embedding(s).
    If `email` is provided, match only that user; otherwise best match among all users.
    On success, returns a short-lived verify_token for /check-liveness.
    """
    try:
        raw = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read upload.",
        ) from exc

    bgr = bytes_to_bgr(raw)
    if bgr is None or not ensure_min_size(bgr):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or too small image.",
        )

    face_count = await asyncio.to_thread(face_service.count_faces_bgr, bgr)
    if face_count is None:
        return VerifyFaceResponse(
            verified=False,
            message="Unable to reliably count faces in frame.",
        )
    if face_count == 0:
        return VerifyFaceResponse(
            verified=False,
            message="No face detected.",
        )
    if face_count > 1:
        return VerifyFaceResponse(
            verified=False,
            message="Multiple faces detected. Stay centered as the only person in frame.",
        )

    try:
        probe = await asyncio.to_thread(face_service.extract_embedding_bgr, bgr)
    except face_service.FaceServiceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if probe is None:
        return VerifyFaceResponse(
            verified=False,
            message="No face detected.",
        )

    users: list[User]
    if email:
        u = db.query(User).filter(User.email == email.lower().strip()).first()
        if not u:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if not bool(u.is_enabled):
            return VerifyFaceResponse(
                verified=False,
                message="Account disabled. Contact administrator.",
            )
        users = [u]
    else:
        users = db.query(User).filter(User.is_enabled.is_(True)).all()
        if not users:
            return VerifyFaceResponse(verified=False, message="No enrolled users.")

    best_user: User | None = None
    best_sim = -1.0
    for u in users:
        try:
            ref = face_service.json_to_embedding(u.face_embedding_json)
        except Exception:
            LOGGER.warning("Bad embedding JSON for user id=%s", u.id)
            continue
        sim = face_service.cosine_similarity(probe, ref)
        if sim > best_sim:
            best_sim = sim
            best_user = u

    if best_user is None or best_sim < settings.FACE_MATCH_THRESHOLD:
        return VerifyFaceResponse(
            verified=False,
            similarity=float(best_sim) if best_user else None,
            message="Face does not match enrolled identity.",
        )

    if not bool(best_user.is_enabled):
        return VerifyFaceResponse(
            verified=False,
            similarity=float(best_sim),
            student_class=best_user.student_class,
            message="Account disabled. Contact administrator.",
        )

    enrol_class = best_user.student_class or ""
    if restrict_to_class and restrict_to_class.strip():
        required = _normalize_class_label(restrict_to_class)
        if not enrol_class or _normalize_class_label(enrol_class) != required:
            return VerifyFaceResponse(
                verified=False,
                similarity=float(best_sim),
                student_class=best_user.student_class,
                message="Detected identity does not match the declared class section.",
            )

    token = auth_service.create_verify_token(best_user.id, best_user.email)
    stored_class = best_user.student_class
    return VerifyFaceResponse(
        verified=True,
        user_id=best_user.id,
        email=best_user.email,
        full_name=best_user.full_name,
        student_class=stored_class,
        similarity=float(best_sim),
        verify_token=token,
        message="Identity verified. Proceed to liveness check.",
    )
