from datetime import timedelta

from ..dependencies import bucket


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    bucket.blob(key).upload_from_string(data, content_type=content_type)


def delete_prefix(prefix: str) -> None:
    for blob in bucket.list_blobs(prefix=prefix):
        blob.delete()


def signed_url(key: str, ttl_seconds: int = 3600) -> str:
    return bucket.blob(key).generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl_seconds),
        method="GET",
    )
