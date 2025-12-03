import os
from app.config import settings
from mcp_use import MCPClient, MCPAgent
from langchain_google_genai import ChatGoogleGenerativeAI

# Simple in-memory cache so we don't recreate client/agent on every message
_AGENT_CACHE: dict[int, MCPAgent] = {}
_ACCESS_TOKEN_CACHE: dict[int, str] = {}


async def create_user_agent(user_id: int, access_token: str) -> MCPAgent:
    """
    Create (or reuse) an MCPAgent configured for the user's Meta token.

    We cache one agent per user_id so that:
    - The MCP client isn't re-created for every chat message.
    - Agent memory can persist across turns within a session.
    """
    # Reuse existing agent if token hasn't changed
    cached_agent = _AGENT_CACHE.get(user_id)
    cached_token = _ACCESS_TOKEN_CACHE.get(user_id)
    if cached_agent is not None and cached_token == access_token:
        return cached_agent

    # load base mcp_config and override env for meta-ads server
    import json
    base = {}
    try:
        with open(settings.MCP_CONFIG_PATH, "r") as f:
            base = json.load(f)
    except Exception:
        base = {}

    # Ensure meta-ads exists and set env
    if "mcpServers" not in base:
        base["mcpServers"] = {}
    base["mcpServers"]["meta-ads"] = base["mcpServers"].get("meta-ads", {})
    base["mcpServers"]["meta-ads"]["env"] = base["mcpServers"]["meta-ads"].get("env", {})
    base["mcpServers"]["meta-ads"]["env"]["META_ACCESS_TOKEN"] = access_token

    # write a temporary config file
    temp_cfg = "./mcp_temp.json"
    with open(temp_cfg, "w") as f:
        json.dump(base, f)

    client = MCPClient.from_config_file(temp_cfg)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2,
    )

    agent = MCPAgent(
        llm=llm,
        client=client,
        max_steps=15,
        memory_enabled=True,
    )

    # Cache for subsequent messages
    _AGENT_CACHE[user_id] = agent
    _ACCESS_TOKEN_CACHE[user_id] = access_token

    return agent
