from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models
from jose import jwt
from app.config import settings
from urllib.parse import urlencode

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return int(user_id)


@router.get("/meta/status")
async def get_meta_connection_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get Meta Ads connection status for settings page."""
    user_id = _require_user_id(request)

    result = await db.execute(
        select(models.Integration)
        .where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
        .order_by(models.Integration.created_at.desc())
    )
    integration = result.scalars().first()

    if not integration:
        return {
            "connected": False,
            "selectedAdAccount": None,
            "adAccountCount": 0,
            "adAccounts": [],
            "selectedAccountDetails": None,
        }

    selected_account_details = None
    if integration.selected_ad_account and integration.ad_accounts:
        selected_account_details = next(
            (
                acct
                for acct in integration.ad_accounts
                if acct.get("id") == integration.selected_ad_account
                or acct.get("account_id") == integration.selected_ad_account
            ),
            None,
        )

    return {
        "connected": True,
        "selectedAdAccount": integration.selected_ad_account,
        "adAccountCount": len(integration.ad_accounts or []),
        "adAccounts": integration.ad_accounts or [],
        "selectedAccountDetails": selected_account_details,
    }


@router.get("/meta/oauth/start")
async def start_meta_oauth_from_settings(request: Request):
    """Start Meta OAuth flow from settings page. Returns auth URL with state token."""
    user_id = _require_user_id(request)

    # Create state token with user_id and redirect destination
    state_data = {
        "id": user_id,
        "redirect": "settings",  # Indicate this is from settings page
    }
    state_token = jwt.encode(state_data, settings.SECRET_KEY, algorithm="HS256")

    # Build OAuth URL with state parameter
    from app.services.meta_service import start_oauth
    base_oauth_url = start_oauth()["url"]
    
    # Add state parameter to the URL (check if URL already has query params)
    if "?" in base_oauth_url:
        oauth_url_with_state = f"{base_oauth_url}&state={state_token}"
    else:
        oauth_url_with_state = f"{base_oauth_url}?state={state_token}"

    return {"authUrl": oauth_url_with_state}


@router.post("/meta/disconnect")
async def disconnect_meta(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Meta Ads integration."""
    user_id = _require_user_id(request)

    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = result.scalars().first()

    if integration:
        await db.delete(integration)
        await db.commit()

    return {"success": True, "message": "Meta Ads disconnected successfully"}



