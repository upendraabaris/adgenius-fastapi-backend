import os
import httpx
from urllib.parse import urlencode


def start_oauth():
    params = {
        "client_id": os.getenv("META_APP_ID"),
        "redirect_uri": os.getenv("META_REDIRECT_URI"),
        "scope": "ads_read,ads_management,business_management",
        "auth_type": "rerequest",
    }
    url = f"https://www.facebook.com/v20.0/dialog/oauth?{urlencode(params)}"
    return {"url": url}


async def exchange_code_for_token(code: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "client_id": os.getenv("META_APP_ID"),
                "client_secret": os.getenv("META_APP_SECRET"),
                "redirect_uri": os.getenv("META_REDIRECT_URI"),
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_ad_accounts(access_token: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/me/adaccounts",
            params={"access_token": access_token},
        )
        resp.raise_for_status()
        return resp.json()["data"]
