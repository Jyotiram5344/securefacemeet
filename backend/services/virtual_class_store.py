"""JSON persistence for scheduled virtual class sessions (Jitsi room metadata)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from config import get_settings

_settings = get_settings()
LOGGER = logging.getLogger(__name__)


def _meetings_path() -> Path:
    base = Path(_settings.VIRTUAL_CLASS_DATA_DIR).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base / "active_meetings.json"


def load_meetings() -> dict[str, Any]:
    path = _meetings_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        meetings = data if isinstance(data, dict) else {}
        # Keep persisted schedule clean when API is accessed.
        active, removed = _split_active_and_expired(meetings)
        if removed:
            save_meetings(active)
        return active
    except (json.JSONDecodeError, OSError):
        return {}


def save_meetings(data: dict[str, Any]) -> None:
    path = _meetings_path()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def _split_active_and_expired(meetings: dict[str, Any], now: float | None = None) -> tuple[dict[str, Any], list[str]]:
    t = time.time() if now is None else now
    active: dict[str, Any] = {}
    removed: list[str] = []
    for room_id, blob in meetings.items():
        end_raw = blob.get("end_time") if isinstance(blob, dict) else None
        try:
            end_t = float(end_raw)
        except (TypeError, ValueError):
            # Keep malformed rows instead of deleting them silently.
            active[room_id] = blob
            continue
        if end_t <= t:
            removed.append(room_id)
        else:
            active[room_id] = blob
    return active, removed


def prune_expired_meetings(now: float | None = None) -> int:
    """
    Remove meetings whose configured end_time has passed.
    Returns number of removed room IDs.
    """
    path = _meetings_path()
    if not path.is_file():
        return 0
    meetings = load_meetings()
    active, removed = _split_active_and_expired(meetings, now)
    if removed:
        save_meetings(active)
        LOGGER.info("Auto-pruned %d expired meeting(s): %s", len(removed), ", ".join(removed))
    return len(removed)


def minutes_left(end_time: float, now: float | None = None) -> float:
    t = time.time() if now is None else now
    return (end_time - t) / 60.0


def scheduled_duration_seconds(room_id: str) -> float:
    """Nominal session length from virtual-class store; 0 if room is not scheduled there."""
    meetings = load_meetings()
    blob = meetings.get(room_id)
    if not blob:
        return 0.0
    try:
        start_t = float(blob.get("start_time", 0))
        end_t = float(blob.get("end_time", 0))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, end_t - start_t)


def attendance_window_open(end_time: float, now: float | None = None) -> bool:
    """Match app2: last 15 minutes through a short grace after end."""
    m = minutes_left(end_time, now)
    return m <= 15.0 and m >= -10.0
