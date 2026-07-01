from fastapi import APIRouter

from app.config import SERVICE_NAME, SERVICE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": SERVICE_NAME, "version": SERVICE_VERSION}
