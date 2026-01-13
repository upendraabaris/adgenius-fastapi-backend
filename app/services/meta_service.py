import os
import httpx
from urllib.parse import urlencode
from app.mcp_utils import create_user_client


def start_oauth():
    params = {
        "client_id": os.getenv("META_APP_ID"),
        "redirect_uri": os.getenv("META_REDIRECT_URI"),
        "scope": "ads_read",
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
    """Fetch ad accounts from Meta API with all necessary fields including name and currency."""
    async with httpx.AsyncClient() as client:
        # First, get basic account list
        resp = await client.get(
            "https://graph.facebook.com/v20.0/me/adaccounts",
            params={
                "access_token": access_token,
                "fields": "id,account_id,name,account_status,currency"
            },
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        
        formatted_accounts = []
        for account in data:
            # Handle different response formats from Meta API
            # Meta API can return 'id' as either numeric or with 'act_' prefix
            account_id_raw = account.get("id", "")
            account_id_from_api = account.get("account_id", "")
            
            # Normalize account_id - remove act_ prefix if present to get numeric ID
            numeric_id = account_id_raw.replace("act_", "") if account_id_raw.startswith("act_") else account_id_raw
            if account_id_from_api and not account_id_from_api.startswith("act_"):
                numeric_id = account_id_from_api.replace("act_", "") if account_id_from_api.startswith("act_") else account_id_from_api
            
            # Format account_id with act_ prefix
            account_id_formatted = f"act_{numeric_id}" if numeric_id and not numeric_id.startswith("act_") else numeric_id
            
            # Get name and currency from initial response
            name = account.get("name", "")
            currency = account.get("currency", "")
            
            # ALWAYS fetch account details individually to ensure we get name and currency
            # Meta API /me/adaccounts sometimes doesn't return these fields reliably
            try:
                # Use the formatted account_id for API call
                api_account_id = account_id_formatted
                account_details_resp = await client.get(
                    f"https://graph.facebook.com/v20.0/{api_account_id}",
                    params={
                        "access_token": access_token,
                        "fields": "name,currency,account_id,id"
                    },
                )
                account_details_resp.raise_for_status()
                account_details = account_details_resp.json()
                
                # Update name and currency from individual account fetch
                if account_details.get("name"):
                    name = account_details.get("name", "")
                if account_details.get("currency"):
                    currency = account_details.get("currency", "USD")
                    
                print(f"Fetched account details for {api_account_id}: name={name}, currency={currency}")
            except Exception as e:
                print(f"Error fetching details for account {account_id_formatted}: {e}")
                # Use defaults if fetch fails
                if not currency:
                    currency = "USD"
                # If we still don't have name from initial response, try to use account_id as name
                if not name:
                    name = f"Account {numeric_id}"
            
            # Build formatted account object
            formatted_account = {
                "id": numeric_id,  # Keep numeric ID (without act_ prefix) for internal use
                "account_id": account_id_formatted,  # Formatted account_id with act_ prefix
                "name": name or "",  # Account name (empty string if not available)
                "currency": currency or "USD",  # Currency code (default to USD)
                "account_status": account.get("account_status", ""),  # Account status
            }
            formatted_accounts.append(formatted_account)
        
        return formatted_accounts


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
                    "fields": "spend,impressions,clicks,ctr,cpc,actions,action_values,reach,frequency,purchase_roas",
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
                    "fields": "campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,actions,action_values,reach,frequency,purchase_roas",
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