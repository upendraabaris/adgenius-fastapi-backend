from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from app.db import AsyncSessionLocal
from app import models
from app.services.meta_service import get_ad_accounts
from app.mcp_utils import create_user_client
from app.utils.auth import _require_user_id, _get_user_subscription
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


@router.get("/meta/adaccounts/mcp")
async def list_meta_ad_accounts_mcp(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Return Meta ad accounts using the MCP server tool `get_ad_accounts`.
    This avoids exposing the raw Meta access token to the frontend.
    """
    user_id = _require_user_id(request)

    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = result.scalars().first()
    if not integration or not integration.access_token:
        raise HTTPException(status_code=400, detail="Meta integration not found or access token not available")

    try:
        client = await create_user_client(user_id, integration.access_token)
        # MCP tool takes no args
        mcp_result = await client.call_tool("meta-ads", "get_ad_accounts", {})

        # MCP server wraps tool output inside `content[0].text` as JSON string
        import json

        content = mcp_result.get("content") if isinstance(mcp_result, dict) else None
        first_text = None
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                first_text = first.get("text")

        if not first_text:
            raise HTTPException(status_code=500, detail="MCP returned empty ad accounts response")

        # Tool returns JSON in text field on success, and plain error text on failure
        try:
            parsed = json.loads(first_text)
        except json.JSONDecodeError:
            # If MCP returned error, include tool text as detail
            raise HTTPException(status_code=500, detail=first_text)

        accounts = parsed.get("accounts", [])
        return {"success": True, "adAccounts": accounts, "total": len(accounts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ad accounts via MCP: {str(e)}")

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
        # Get subscription plan
        sub = await _get_user_subscription(db, user_id)
        plan = sub.plan if sub else "free"
        
        # Mapping frontend plan keys to backend logic if necessary
        # UI uses: free, starter, growth, enterprise
        
        # Define limits
        limits = {
            "free": 1,
            "starter": 1,
            "growth": 5,
            "enterprise": 999
        }
        account_limit = limits.get(plan, 1)

        result = await db.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
                models.Integration.provider == "meta"
            )
        )
        integration = result.scalars().first()
        
        if not integration:
            raise HTTPException(status_code=404, detail="Meta integration not found")

        # Handle FREE plan locking logic
        if plan == "free" and integration.is_account_locked:
            # Check if attempting to change to a DIFFERENT account
            currently_selected = integration.selected_ad_accounts or []
            if payload.account_id not in currently_selected:
                raise HTTPException(
                    status_code=403, 
                    detail="On the Free plan, you cannot change your selected ad account once saved. Please upgrade for more flexibility."
                )

        # Validate account ID exists in fetched ad_accounts
        if integration.ad_accounts:
            valid_ids = {acct.get("id") for acct in integration.ad_accounts} | {acct.get("account_id") for acct in integration.ad_accounts}
            if payload.account_id not in valid_ids:
                raise HTTPException(status_code=400, detail="Invalid ad account id")

        # Manage the selected_ad_accounts list
        selected_list = integration.selected_ad_accounts or []
        
        if payload.account_id not in selected_list:
            if len(selected_list) >= account_limit:
                raise HTTPException(
                    status_code=403, 
                    detail=f"You have reached the maximum number of selected accounts ({account_limit}) for your {plan} plan."
                )
            selected_list.append(payload.account_id)
        
        # Update and lock if free
        integration.selected_ad_accounts = selected_list
        if plan == "free" and len(selected_list) > 0:
            integration.is_account_locked = True
            
        await db.commit()
        
        return {"ok": True, "selectedAccounts": selected_list, "limit": account_limit}
        
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
