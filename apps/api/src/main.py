import base64
import json

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="text-digest-v2 api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        print(f"id token: {token}", flush=True)
        parts = token.split(".")
        if len(parts) >= 2:
            # Base64url-decode the JWT payload (no signature verification).
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            print(f"token claims:\n{json.dumps(claims, indent=2)}", flush=True)
    return {"status": "ok"}
