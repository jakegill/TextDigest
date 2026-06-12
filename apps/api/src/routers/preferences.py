import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, status

from ..middleware.auth import get_current_uid
from ..models.preferences import Preferences
from ..services.preferences import service

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(
    uid: Annotated[str, Depends(get_current_uid)],
) -> Preferences:
    return await asyncio.to_thread(service.get_for_user, uid)


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
async def put_preferences(
    body: Preferences,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(service.set_for_user, uid, body)
