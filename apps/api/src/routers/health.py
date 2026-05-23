import base64
import json
import logging

from fastapi import APIRouter, Header

logger = logging.getLogger("uvicorn.error")
router = APIRouter()


@router.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        logger.info("id token: %s", token)
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            logger.info("token claims:\n%s", json.dumps(claims, indent=2))
    return {"status": "ok"}
