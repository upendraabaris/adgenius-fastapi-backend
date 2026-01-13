from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from app.db import AsyncSessionLocal
from app import models
from app.services.meta_service import get_ad_accounts

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id

class AccountSelection(BaseModel):
    account_id: str

@router.get("/meta/adaccounts")
async def list_meta_ad_accounts(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    user_id = _require_user_id(request)
    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta"
        )
    )
    integration = result.scalars().first()
    if not integration or not integration.ad_accounts:
        return {"adAccounts": []}
    return {"adAccounts": integration.ad_accounts}

@router.get("/meta/access-token")
async def get_meta_access_token(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get Meta access token for frontend to make direct API calls."""
    user_id = _require_user_id(request)
    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta"
        )
    )
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(status_code=404, detail="Meta integration not found")
    
    if not integration.access_token:
        raise HTTPException(status_code=400, detail="Access token not available")
    
    return {
        "access_token": integration.access_token,
        "connected": True
    }

@router.post("/meta/refresh-accounts")
async def refresh_meta_ad_accounts(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Refresh ad accounts data from Meta API to get updated name and currency."""
    user_id = _require_user_id(request)
    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta"
        )
    )
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(status_code=404, detail="Meta integration not found")
    
    if not integration.access_token:
        raise HTTPException(status_code=400, detail="Access token not available")
    
    try:
        # Fetch fresh account data from Meta API
        ad_accounts = await get_ad_accounts(integration.access_token)
        
        # Update integration with fresh account data
        integration.ad_accounts = ad_accounts
        await db.commit()
        
        return {
            "success": True,
            "message": "Ad accounts refreshed successfully",
            "adAccounts": ad_accounts
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to refresh accounts: {str(e)}")

@router.post("/select-account")
async def select_meta_account(
    request: Request,
    payload: AccountSelection,
    db: AsyncSession = Depends(get_db)
):
    user_id = _require_user_id(request)

    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta"
        )
    )
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(status_code=404, detail="Meta integration not found")

    # Optional safety: ensure requested account exists
    if integration.ad_accounts:
        valid_ids = {acct.get("id") for acct in integration.ad_accounts}
        if payload.account_id not in valid_ids:
            raise HTTPException(status_code=400, detail="Invalid ad account id")

    await db.execute(
        update(models.Integration)
        .where(models.Integration.id == integration.id)
        .values(selected_ad_account=payload.account_id)
    )
    await db.commit()

    return {"ok": True, "selectedAccount": payload.account_id}
