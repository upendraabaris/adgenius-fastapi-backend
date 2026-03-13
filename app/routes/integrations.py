from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from app.db import AsyncSessionLocal
from app import models
from app.services.meta_service import get_ad_accounts
import httpx

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

class MetaConnectionPayload(BaseModel):
    access_token: str

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
    
    try:
        result = await db.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
                models.Integration.provider == "meta"
            )
        )
        integration = result.scalars().first()
        
        if not integration:
            raise HTTPException(status_code=404, detail="Meta integration not found")

        print(f"📋 Selecting account {payload.account_id} for user {user_id}")

        # Validate account ID exists in ad_accounts
        if integration.ad_accounts:
            valid_ids = {acct.get("id") for acct in integration.ad_accounts} | {acct.get("account_id") for acct in integration.ad_accounts}
            
            if payload.account_id not in valid_ids:
                print(f"❌ Invalid account ID: {payload.account_id}")
                print(f"❌ Valid IDs: {valid_ids}")
                raise HTTPException(status_code=400, detail="Invalid ad account id")

        print(f"💾 Updating integration with account: {payload.account_id}")
        
        await db.execute(
            update(models.Integration)
            .where(models.Integration.id == integration.id)
            .values(selected_ad_account=payload.account_id)
        )
        await db.commit()
        
        print(f"✅ Account selected successfully")

        return {"ok": True, "selectedAccount": payload.account_id}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error selecting account: {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to select account: {str(e)}")


@router.post("/meta/save")
async def save_meta_connection(
    request: Request,
    payload: MetaConnectionPayload,
    db: AsyncSession = Depends(get_db)
):
    """
    Save Meta connection from frontend SDK authentication.
    1. Validate access token with Meta API
    2. Fetch ad accounts
    3. Save to database
    """
    user_id = _require_user_id(request)
    
    try:
        # Validate token by fetching user info from Meta
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.facebook.com/v20.0/me",
                params={"access_token": payload.access_token, "fields": "id,name,email"}
            )
            resp.raise_for_status()
            user_info = resp.json()
            
        print(f"✅ Meta token validated for user: {user_info.get('name')} (ID: {user_info.get('id')})")
        
        # Fetch ad accounts
        ad_accounts = await get_ad_accounts(payload.access_token)
        print(f"✅ Fetched {len(ad_accounts)} ad accounts from Meta")
        
        # Upsert integration
        result = await db.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
                models.Integration.provider == "meta"
            )
        )
        integration = result.scalars().first()
        
        if integration:
            print(f"🔄 Updating existing Meta integration for user {user_id}")
            integration.access_token = payload.access_token
            integration.ad_accounts = ad_accounts
        else:
            print(f"✨ Creating new Meta integration for user {user_id}")
            integration = models.Integration(
                user_id=user_id,
                provider="meta",
                access_token=payload.access_token,
                ad_accounts=ad_accounts,
            )
            db.add(integration)
        
        await db.commit()
        await db.refresh(integration)
        
        return {
            "success": True,
            "message": "Meta connection saved successfully",
            "ad_accounts": ad_accounts,
            "ad_account_count": len(ad_accounts),
            "meta_user": user_info
        }
        
    except httpx.HTTPStatusError as e:
        print(f"❌ Meta API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=400, detail="Invalid access token or Meta API error")
    except Exception as e:
        print(f"❌ Error saving Meta connection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save connection: {str(e)}")
