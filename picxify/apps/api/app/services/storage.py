from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings

PRESIGN_EXPIRY_SECONDS = 900


@dataclass(frozen=True)
class ObjectStat:
    size_bytes: int
    etag: str | None = None


class StorageService:
    """S3-compatible object storage (MinIO in dev, S3/R2 in production).

    Raw uploads are private; clients only ever touch them through presigned URLs.
    """

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


@lru_cache
def _default_storage() -> StorageService:
    return StorageService()


def get_storage() -> StorageService:
    """FastAPI dependency; overridden with a fake in tests."""
    return _default_storage()
