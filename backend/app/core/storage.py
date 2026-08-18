import uuid
from functools import lru_cache

import boto3

from app.core.config import Settings, get_settings


class RawArtifactStore:
    """Thin wrapper around the S3-compatible (MinIO) client. Raw crawled
    HTML and raw AI provider responses live here — normalized/structured
    data lives in Postgres, never the other way around."""

    def __init__(self, settings: Settings):
        self._bucket = settings.s3_bucket_raw_artifacts
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        )

    def ensure_bucket(self) -> None:
        existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
        if self._bucket not in existing:
            self._client.create_bucket(Bucket=self._bucket)

    def put_text(self, key_prefix: str, content: str, content_type: str = "text/html") -> str:
        key = f"{key_prefix}/{uuid.uuid4()}"
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
        return f"s3://{self._bucket}/{key}"

    def put_bytes(self, key_prefix: str, content: bytes, content_type: str) -> str:
        key = f"{key_prefix}/{uuid.uuid4()}"
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        return f"s3://{self._bucket}/{key}"

    def presigned_url(self, uri: str, expires_seconds: int = 3600) -> str:
        prefix = f"s3://{self._bucket}/"
        if not uri.startswith(prefix):
            raise ValueError("artifact does not belong to the configured bucket")
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": uri[len(prefix):]}, ExpiresIn=expires_seconds
        )

    def get_text(self, uri: str) -> str:
        """Read a UTF-8 text artifact without exposing storage credentials."""
        prefix = f"s3://{self._bucket}/"
        if not uri.startswith(prefix):
            raise ValueError("artifact does not belong to the configured bucket")
        response = self._client.get_object(Bucket=self._bucket, Key=uri[len(prefix):])
        return response["Body"].read().decode("utf-8", errors="replace")


@lru_cache
def get_storage() -> RawArtifactStore:
    return RawArtifactStore(get_settings())
