from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

PRESIGN_EXPIRY_SECONDS = 900


@dataclass(frozen=True)
class ObjectStat:
    size_bytes: int
    etag: str | None = None


class StorageService(Protocol):
    """Object storage contract. Two implementations: S3-compatible (MinIO/S3/
    R2, real infra) and local-disk (no infra at all — for a laptop with no
    Docker). Raw uploads are private; clients only ever touch them through
    presigned URLs."""

    def presign_put(self, object_key: str, content_type: str | None) -> str: ...
    def presign_get(self, object_key: str) -> str: ...
    def get_bytes(self, object_key: str) -> bytes: ...
    def put_bytes(self, object_key: str, data: bytes, content_type: str | None = None) -> None: ...
    def stat_object(self, object_key: str) -> ObjectStat | None: ...


class S3StorageService:
    """S3-compatible object storage (MinIO in dev, S3/R2 in production)."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            ),
        )
        self._bucket = settings.s3_bucket

    def presign_put(self, object_key: str, content_type: str | None) -> str:
        params: dict = {"Bucket": self._bucket, "Key": object_key}
        if content_type:
            params["ContentType"] = content_type
        return self._client.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=PRESIGN_EXPIRY_SECONDS
        )

    def presign_get(self, object_key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=PRESIGN_EXPIRY_SECONDS,
        )

    def get_bytes(self, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        return response["Body"].read()

    def put_bytes(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        params: dict = {"Bucket": self._bucket, "Key": object_key, "Body": data}
        if content_type:
            params["ContentType"] = content_type
        self._client.put_object(**params)

    def stat_object(self, object_key: str) -> ObjectStat | None:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=object_key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectStat(size_bytes=head["ContentLength"], etag=head.get("ETag"))


class LocalDiskStorageService:
    """Plain files on disk under `local_storage_dir` — no object store at
    all. There is no real presigned URL for a local file, so `presign_put`/
    `presign_get` point at `PUT`/`GET /local-storage/{key}` on this same API
    process instead (see `app/routers/local_storage.py`); the browser still
    does a direct PUT/GET, it just lands on the API instead of MinIO/S3.

    Dev-only: never set STORAGE_BACKEND=local in production — these routes
    have no auth (the object key's embedded UUIDs are the only obscurity)."""

    def __init__(self) -> None:
        self._root = Path(settings.local_storage_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        # object_key is server-generated (uuid-based); still resolve and
        # confirm containment before touching disk, as a defense-in-depth
        # measure against a malformed key ever reaching here.
        path = (self._root / object_key).resolve()
        if self._root not in path.parents and path != self._root:
            raise ValueError(f"Refusing to touch a path outside local storage: {object_key!r}")
        return path

    def presign_put(self, object_key: str, content_type: str | None) -> str:
        return f"{settings.api_url}/local-storage/{object_key}"

    def presign_get(self, object_key: str) -> str:
        return f"{settings.api_url}/local-storage/{object_key}"

    def get_bytes(self, object_key: str) -> bytes:
        return self._path(object_key).read_bytes()

    def put_bytes(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def stat_object(self, object_key: str) -> ObjectStat | None:
        path = self._path(object_key)
        if not path.is_file():
            return None
        return ObjectStat(size_bytes=path.stat().st_size)


@lru_cache
def _default_storage() -> StorageService:
    if settings.storage_backend == "local":
        return LocalDiskStorageService()
    return S3StorageService()


def get_storage() -> StorageService:
    """FastAPI dependency; overridden with a fake in tests."""
    return _default_storage()
