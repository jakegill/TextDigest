from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, titles

app = FastAPI(title="text-digest-v2 api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(titles.router)
