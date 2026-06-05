"""Compatibility entrypoint for `uvicorn app.main:app --reload`."""
from main import app

__all__ = ["app"]
