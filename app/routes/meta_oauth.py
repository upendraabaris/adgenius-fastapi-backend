from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.services.meta_service import start_oauth, exchange_code_for_token, get_ad_accounts
from app.models import Integration
from app.config import settings
from jose import jwt, JWTError
import os
from fastapi import FastAPI, Query, HTTPException

router = APIRouter(prefix="/api/meta", tags=["Meta OAuth"])

# Define get_db to yield a database session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --------------------------
# Step 1: Start OAuth
# --------------------------
@router.get("/oauth/start")
async def oauth_start():
    result = start_oauth()
    return {"authUrl": result["url"]}

# --------------------------
# Step 2: OAuth Callback
# --------------------------
@router.get("/oauth/callback")
async def oauth_callback(code: str = None, state: str = None, db: AsyncSession = Depends(get_db)):
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state token")

    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload.get("id") or payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid state token")

    # Exchange code → token
    token_data = await exchange_code_for_token(code)
    access_token = token_data["access_token"]

    # Fetch ad accounts from Meta
    ad_accounts = await get_ad_accounts(access_token)

    # Upsert Integration row for this user/provider without using Postgres-specific APIs
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == "meta"
        )
    )
    integration = result.scalars().first()

    if integration:
        # Update existing integration
        integration.access_token = access_token
        integration.ad_accounts = ad_accounts
    else:
        # Create new integration
        integration = Integration(
            user_id=user_id,
            provider="meta",
            access_token=access_token,
            ad_accounts=ad_accounts,
        )
        db.add(integration)

    await db.commit()
    
    # Verify the integration was saved
    verify_result = await db.execute(
        select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == "meta"
        )
    )
    saved_integration = verify_result.scalars().first()
    if not saved_integration:
        raise HTTPException(status_code=500, detail="Failed to save integration")

    frontend = os.getenv("FRONTEND_URL", "http://localhost:5176")
    
    # Check if redirect destination is in state token
    redirect_to = payload.get("redirect", "onboarding")
    
    if redirect_to == "settings":
        # Redirect to settings page with success message (using hash to avoid #_=_ from Meta)
        return RedirectResponse(f"{frontend}/settings?meta_connected=success", status_code=302)
    else:
        # Default redirect to onboarding
        return RedirectResponse(f"{frontend}/onboarding?connected=meta", status_code=302)


@router.get("/test/ad-accounts")
async def test_ad_accounts(access_token: str = Query(...)):
    """Test endpoint to see raw Meta API response and formatted data."""
    try:
        import httpx
        # Get raw response first
        async with httpx.AsyncClient() as client:
            raw_resp = await client.get(
                "https://graph.facebook.com/v20.0/me/adaccounts",
                params={
                    "access_token": access_token,
                    "fields": "id,account_id,name,account_status,currency"
                },
            )
            raw_resp.raise_for_status()
            raw_data = raw_resp.json().get("data", [])
        
        # Get formatted data
        formatted_data = await get_ad_accounts(access_token)
        
        return {
            "success": True,
            "raw_count": len(raw_data),
            "formatted_count": len(formatted_data),
            "raw_response": raw_data,  # Show what Meta API actually returns
            "formatted_response": formatted_data,  # Show our formatted data
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
