"""
SecureFaceMeet — FastAPI entrypoint.
Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from routes import admin_routes, face_routes, liveness_routes, meeting_routes, monitoring_routes, virtual_class_routes
from services import virtual_class_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    async def _meeting_prune_worker() -> None:
        # Run lightweight pruning loop so expired meetings disappear automatically.
        while not stop_event.is_set():
            try:
                virtual_class_store.prune_expired_meetings()
            except Exception:
                LOGGER.exception("Virtual-class prune loop failed.")
            await asyncio.sleep(1)

    try:
        init_db()
        LOGGER.info("Database tables ensured.")
    except Exception:
        LOGGER.exception("Database init failed — check DATABASE_URL.")
    worker_task = asyncio.create_task(_meeting_prune_worker())
    yield
    stop_event.set()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(face_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(liveness_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(meeting_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(monitoring_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(virtual_class_routes.router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
def health() -> dict:
    try:
        from services import liveness_service

        liveness_ok = liveness_service.is_liveness_available()
    except Exception:
        liveness_ok = False
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "liveness_model_loaded": liveness_ok,
    }

@app.get("/")
def root() -> dict:
    return {"message": "SecureFaceMeet API", "docs": "/docs"}
