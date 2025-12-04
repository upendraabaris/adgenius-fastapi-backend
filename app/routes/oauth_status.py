from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models


router = APIRouter(prefix="/api/oauth", tags=["oauth"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


@router.get("/status")
async def get_oauth_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = result.scalars().first()

    if not integration:
        return {"connected": False, "selectedAdAccount": None, "adAccountCount": 0}

    return {
        "connected": True,
        "selectedAdAccount": integration.selected_ad_account,
        "adAccountCount": len(integration.ad_accounts or []),
    }

