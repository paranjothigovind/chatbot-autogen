"""Authenticated identity probe."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_principal

router = APIRouter(prefix="/api", tags=["identity"])


@router.get("/me")
async def me(principal: Annotated[Principal, Depends(get_principal)]) -> dict[str, str]:
    """Return the caller's id as derived from the validated token."""
    return {"user_id": principal.user_id}
