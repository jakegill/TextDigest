import os
from typing import Annotated

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth
from google.cloud import firestore, storage

DATA_BUCKET = os.environ["DATA_BUCKET"]
MINERU_URL = os.environ["MINERU_URL"]
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ["PROJECT_ID"]
STAGE = os.environ["STAGE"]
FIRESTORE_DATABASE = f"td-{STAGE}"

storage_client = storage.Client()
bucket = storage_client.bucket(DATA_BUCKET)

firestore_client = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)

firebase_admin.initialize_app(options={"projectId": PROJECT_ID})


def get_current_uid(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = firebase_auth.verify_id_token(authorization.removeprefix("Bearer "))
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid id token") from exc
    return claims["uid"]
