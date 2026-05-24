from typing import Annotated

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth

from ..dependencies import PROJECT_ID

firebase_admin.initialize_app(options={"projectId": PROJECT_ID})


def get_current_uid(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = firebase_auth.verify_id_token(authorization.removeprefix("Bearer "))
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid id token") from exc
    return claims["uid"]
