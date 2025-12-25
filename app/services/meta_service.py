import os
import httpx
from urllib.parse import urlencode
from app.mcp_utils import create_user_client


def start_oauth():
    params = {
        "client_id": os.getenv("META_APP_ID"),
        "redirect_uri": os.getenv("META_REDIRECT_URI"),
        "scope": "ads_read,ads_management",
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


async def get_campaigns(user_id: int, access_token: str, account_id: str):
    """Fetch campaigns for a given ad account using MCP with better error handling."""
    try:
        # Use MCP client directly for more reliable results
        client = await create_user_client(user_id, access_token)
        
        # Ensure account_id has 'act_' prefix
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        # Call MCP tool directly
        result = await client.call_tool(
            "meta-ads",
            "get_campaigns", 
            {"account_id": account_id}
        )
        
        if result and isinstance(result, dict):
            campaigns = result.get("content", [])
            if isinstance(campaigns, list):
                return campaigns
            elif isinstance(campaigns, str):
                # Try to parse JSON string
                import json
                try:
                    parsed = json.loads(campaigns)
                    return parsed if isinstance(parsed, list) else []
                except:
                    return []
        
        return []
        
    except Exception as e:
        print(f"MCP Error fetching campaigns: {e}")
        # Fallback to direct API call if MCP fails
        try:
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://graph.facebook.com/v20.0/{account_id}/campaigns",
                    params={
                        "access_token": access_token,
                        "fields": "id,name,status,objective,created_time,updated_time",
                        "limit": 100  # Increased limit to get more campaigns
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
        except Exception as fallback_error:
            print(f"Fallback API Error: {fallback_error}")
            return []


async def get_account_insights(user_id: int, access_token: str, account_id: str, date_preset: str = "last_30d"):
    """Fetch insights/performance data for an ad account with MCP fallback to direct API."""
    try:
        # Try MCP first
        client = await create_user_client(user_id, access_token)
        
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        result = await client.call_tool(
            "meta-ads",
            "get_insights",
            {
                "account_id": account_id,
                "level": "account",
                "date_preset": date_preset
            }
        )
        
        if result and isinstance(result, dict):
            insights = result.get("content", {})
            if isinstance(insights, dict):
                return insights
            elif isinstance(insights, str):
                import json
                try:
                    parsed = json.loads(insights)
                    return parsed if isinstance(parsed, dict) else {}
                except:
                    pass
        
    except Exception as e:
        print(f"MCP Error fetching insights: {e}")
    
    # Fallback to direct API
    try:
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{account_id}/insights",
                params={
                    "access_token": access_token,
                    "fields": "spend,impressions,clicks,ctr,cpc,actions,action_values,reach,frequency",
                    "date_preset": date_preset,
                    "level": "account"
                },
            )
            resp.raise_for_status()
            data = resp.json()
            insights_data = data.get("data", [])
            return insights_data[0] if insights_data else {}
    except Exception as fallback_error:
        print(f"Fallback insights error: {fallback_error}")
        return {}


async def get_campaign_insights(user_id: int, access_token: str, account_id: str, date_preset: str = "last_30d"):
    """Fetch insights for all campaigns with direct API first, MCP as fallback."""
    
    # Try direct API first for better reliability
    try:
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{account_id}/insights",
                params={
                    "access_token": access_token,
                    "fields": "campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,actions,action_values,reach,frequency",
                    "date_preset": date_preset,
                    "level": "campaign"
                },
            )
            resp.raise_for_status()
            data = resp.json()
            insights = data.get("data", [])
            print(f"Direct API: Got {len(insights)} campaign insights")
            return insights
    except Exception as direct_error:
        print(f"Direct API campaign insights error: {direct_error}")
    
    # Fallback to MCP if direct API fails
    try:
        client = await create_user_client(user_id, access_token)
        
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        result = await client.call_tool(
            "meta-ads",
            "get_insights",
            {
                "account_id": account_id,
                "level": "campaign",
                "date_preset": date_preset
            }
        )
        
        if result and isinstance(result, dict):
            insights = result.get("content", [])
            if isinstance(insights, list):
                print(f"MCP: Got {len(insights)} campaign insights")
                return insights
            elif isinstance(insights, str):
                import json
                try:
                    parsed = json.loads(insights)
                    return parsed if isinstance(parsed, list) else []
                except:
                    pass
        
    except Exception as e:
        print(f"MCP Error fetching campaign insights: {e}")
    
    print("Both direct API and MCP failed for campaign insights")
    return []

async def get_campaign_budgets(user_id: int, access_token: str, account_id: str):
    """Fetch campaign budgets and daily spend limits."""
    try:
        # Try MCP first
        client = await create_user_client(user_id, access_token)
        
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        result = await client.call_tool(
            "meta-ads",
            "get_campaigns",
            {
                "account_id": account_id,
                "fields": "id,name,daily_budget,lifetime_budget,budget_remaining"
            }
        )
        
        if result and isinstance(result, dict):
            campaigns = result.get("content", [])
            if isinstance(campaigns, list):
                return campaigns
            elif isinstance(campaigns, str):
                import json
                try:
                    parsed = json.loads(campaigns)
                    return parsed if isinstance(parsed, list) else []
                except:
                    pass
        
    except Exception as e:
        print(f"MCP Error fetching campaign budgets: {e}")
    
    # Fallback to direct API
    try:
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{account_id}/campaigns",
                params={
                    "access_token": access_token,
                    "fields": "id,name,daily_budget,lifetime_budget,budget_remaining,status",
                    "limit": 100
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
    except Exception as fallback_error:
        print(f"Fallback campaign budgets error: {fallback_error}")
        return []