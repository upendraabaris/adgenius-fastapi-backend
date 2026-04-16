"""
Meta OAuth service using Configuration ID instead of App ID
This is separate from the existing meta_service.py which uses App ID
"""
import os
import httpx
from urllib.parse import urlencode


def start_oauth_with_config():
    """Start OAuth flow using Configuration ID"""
    config_id = os.getenv("META_CONFIG_ID")
    redirect_uri = os.getenv("META_CONFIG_REDIRECT_URI")
    
    if not config_id:
        raise ValueError("META_CONFIG_ID not set in environment variables")
    if not redirect_uri:
        raise ValueError("META_CONFIG_REDIRECT_URI not set in environment variables")
    
    # print(f"🔧 Starting OAuth with Configuration ID: {config_id}")
    # print(f"🔧 Redirect URI: {redirect_uri}")
    
    # Configuration ID uses a different URL format
    # Format: https://www.facebook.com/v20.0/dialog/oauth?config_id=XXX&redirect_uri=YYY&response_type=code
    params = {
        "config_id": config_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    url = f"https://www.facebook.com/v20.0/dialog/oauth?{urlencode(params)}"
    # print(f"🔧 Generated OAuth URL: {url}")
    return {"url": url}


async def exchange_code_for_token_with_config(code: str):
    """Exchange authorization code for access token using Configuration ID"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "config_id": os.getenv("META_CONFIG_ID"),
                "redirect_uri": os.getenv("META_CONFIG_REDIRECT_URI"),
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_ad_accounts_with_config(access_token: str, fields: str = "id,name,account_status,currency"):
    """Fetch ad accounts using Configuration ID based token"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://graph.facebook.com/v20.0/me/adaccounts?fields={fields}",
            params={"access_token": access_token},
        )
        resp.raise_for_status()
        return resp.json()["data"]
