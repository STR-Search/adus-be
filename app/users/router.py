from fastapi import APIRouter

import app.users.models  # noqa: F401 — ensures all models are registered with SQLAlchemy

router = APIRouter(prefix="/users", tags=["users"])
