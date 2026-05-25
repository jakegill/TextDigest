from typing import Annotated

import firebase_admin
from fastapi import Header, HTTPException, Request, status
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from ..dependencies import API_SA_EMAIL, PROJECT_ID

firebase_admin.initialize_app(options={"projectId": PROJECT_ID})

_GOOGLE_REQUEST = google_requests.Request()


def get_current_uid(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    
    try:
        claims = firebase_auth.verify_id_token(authorization.removeprefix("Bearer "))
    
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid id token") from exc
    
    return claims["uid"]


def verify_cloud_task_oidc(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Validates the OIDC token Cloud Tasks attaches to dispatched HTTP tasks.
    Expects: signed by Google, audience matches this request's own URL, email
    matches api-sa. Audience is the URL Cloud Tasks targeted, which we mirror
    on our side by using the incoming request's URL as the expected audience."""
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing cloud-task oidc token"
        )
    
    token = authorization.removeprefix("Bearer ")
    expected_audience = str(request.url).split("?", 1)[0]

    try:
        claims = google_id_token.verify_oauth2_token(
            token, _GOOGLE_REQUEST, audience=expected_audience
        )

    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid cloud-task oidc token"
        ) from exc
    
    if claims.get("email") != API_SA_EMAIL:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"oidc token issued to unexpected sa: {claims.get('email')!r}",
        )
