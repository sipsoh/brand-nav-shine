"""PUT/GET targets for LocalDiskStorageService's "presigned" URLs.

Only meaningful when STORAGE_BACKEND=local (a laptop with no Docker/S3);
returns 404 otherwise so these routes are inert against the real S3 backend.
Dev-only — no auth beyond the object key's embedded UUIDs, never enable in
production.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.services.storage import StorageService, get_storage

router = APIRouter(prefix="/local-storage", tags=["local-storage"])


def _require_local_backend() -> None:
    if settings.storage_backend != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.put("/{object_key:path}")
async def put_local_object(
    object_key: str,
    request: Request,
    storage: StorageService = Depends(get_storage),
) -> Response:
    _require_local_backend()
    data = await request.body()
    storage.put_bytes(object_key, data, request.headers.get("content-type"))
    return Response(status_code=status.HTTP_200_OK)


@router.get("/{object_key:path}")
def get_local_object(
    object_key: str,
    storage: StorageService = Depends(get_storage),
) -> Response:
    _require_local_backend()
    try:
        data = storage.get_bytes(object_key)
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found.")
    return Response(content=data, media_type="application/octet-stream")
