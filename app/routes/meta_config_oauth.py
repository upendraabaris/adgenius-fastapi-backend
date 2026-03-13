"""
Meta OAuth routes using Configuration ID
This is separate from meta_oauth.py which uses App ID
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.services.meta_config_service import (
    start_oauth_with_config,
    exchange_code_for_token_with_config,
    get_ad_accounts_with_config
)
from app.models import Integration
from app.config import settings
from jose import jwt, JWTError
import os

router = APIRouter(prefix="/api/meta-config", tags=["Meta Config OAuth"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.get("/oauth/start")
async def oauth_start_with_config():
    """Start OAuth flow using Configuration ID"""
    try:
        result = start_oauth_with_config()
        return {"authUrl": result["url"], "debug": {
            "config_id": os.getenv("META_CONFIG_ID"),
            "redirect_uri": os.getenv("META_CONFIG_REDIRECT_URI")
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start OAuth: {str(e)}")


@router.get("/oauth/callback")
async def oauth_callback_with_config(
    code: str = None,
    state: str = None,
    db: AsyncSession = Depends(get_db)
):
    """OAuth callback handler for Configuration ID based flow"""
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state token")

    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload.get("id") or payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid state token")

    # Exchange code for token using Configuration ID
    token_data = await exchange_code_for_token_with_config(code)
    access_token = token_data["access_token"]

    # Fetch ad accounts from Meta
    ad_accounts = await get_ad_accounts_with_config(access_token)

    # Upsert Integration row for this user/provider
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
        return RedirectResponse(
            f"{frontend}/settings?meta_connected=success",
            status_code=302
        )
    else:
        return RedirectResponse(
            f"{frontend}/onboarding?connected=meta",
            status_code=302
        )
