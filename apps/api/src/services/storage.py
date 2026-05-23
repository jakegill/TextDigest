from ..dependencies import bucket


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    bucket.blob(key).upload_from_string(data, content_type=content_type)
