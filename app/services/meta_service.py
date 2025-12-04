import os
import httpx
from urllib.parse import urlencode
from app.mcp_utils import create_user_client


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


async def get_campaigns(user_id: int, access_token: str, account_id: str):
    """Fetch campaigns for a given ad account using MCP."""
    from app.mcp_utils import create_user_agent
    
    # Use MCPAgent to call MCP tools
    agent = await create_user_agent(user_id, access_token)
    
    # Use agent to get campaigns data
    prompt = f"List all campaigns for ad account {account_id}. Return only the campaign data as JSON array with fields: id, name, status, objective. Do not include any explanation, just the JSON array."
    
    try:
        result = await agent.run(prompt)
        # Parse the result - agent returns text, we need to extract JSON
        import json
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            campaigns = json.loads(json_match.group())
            return campaigns if isinstance(campaigns, list) else []
        
        # If no JSON found, try to parse the whole response
        try:
            campaigns = json.loads(result)
            return campaigns if isinstance(campaigns, list) else []
        except:
            return []
    except Exception as e:
        return []


async def get_account_insights(user_id: int, access_token: str, account_id: str, date_preset: str = "last_30d"):
    """Fetch insights/performance data for an ad account using MCP."""
    from app.mcp_utils import create_user_agent
    
    # Use MCPAgent to call MCP tools
    agent = await create_user_agent(user_id, access_token)
    
    # Use agent to get account insights
    prompt = f"Get account-level insights for ad account {account_id} for {date_preset}. Return only the insights data as JSON object with fields: spend, impressions, clicks, ctr, cpc, actions, action_values. Do not include any explanation, just the JSON object."
    
    try:
        result = await agent.run(prompt)
        # Parse the result
        import json
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            insights = json.loads(json_match.group())
            # If it's a list, take first item
            if isinstance(insights, list) and len(insights) > 0:
                return insights[0]
            return insights if isinstance(insights, dict) else {}
        
        # If no JSON found, try to parse the whole response
        try:
            insights = json.loads(result)
            if isinstance(insights, list) and len(insights) > 0:
                return insights[0]
            return insights if isinstance(insights, dict) else {}
        except:
            return {}
    except Exception as e:
        return {}


async def get_campaign_insights(user_id: int, access_token: str, account_id: str, date_preset: str = "last_30d"):
    """Fetch insights for all campaigns in an ad account using MCP."""
    from app.mcp_utils import create_user_agent
    
    # Use MCPAgent to call MCP tools
    agent = await create_user_agent(user_id, access_token)
    
    # Use agent to get campaign insights
    prompt = f"Get campaign-level insights for ad account {account_id} for {date_preset}. Return only the insights data as JSON array with fields: campaign_id, campaign_name, spend, impressions, clicks, ctr, cpc, actions, action_values. Do not include any explanation, just the JSON array."
    
    try:
        result = await agent.run(prompt)
        # Parse the result
        import json
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            insights = json.loads(json_match.group())
            return insights if isinstance(insights, list) else []
        
        # If no JSON found, try to parse the whole response
        try:
            insights = json.loads(result)
            return insights if isinstance(insights, list) else []
        except:
            return []
    except Exception as e:
        return []