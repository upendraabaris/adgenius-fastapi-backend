import os
import asyncio
import logging
from typing import Optional
from app.config import settings
from mcp_use import MCPClient, MCPAgent
# from langchain_google_genai import ChatGoogleGenerativeAI  # Commented out - using Claude instead
from langchain_aws import ChatBedrock

# Setup logging
logger = logging.getLogger(__name__)

# Simple in-memory cache so we don't recreate client/agent on every message
_AGENT_CACHE: dict[int, MCPAgent] = {}
_ACCESS_TOKEN_CACHE: dict[int, str] = {}
_CLIENT_CACHE: dict[int, MCPClient] = {}
_AGENT_INITIALIZATION_TASKS: dict[int, asyncio.Task] = {}

# Pre-load base config to avoid file I/O on every request
_BASE_CONFIG_CACHE = None

def _get_base_config():
    """Get base MCP config with caching to avoid repeated file reads."""
    global _BASE_CONFIG_CACHE
    if _BASE_CONFIG_CACHE is None:
        import json
        try:
            with open(settings.MCP_CONFIG_PATH, "r") as f:
                _BASE_CONFIG_CACHE = json.load(f)
        except Exception:
            _BASE_CONFIG_CACHE = {}
    return _BASE_CONFIG_CACHE.copy()  # Return copy to avoid mutations


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
        logger.info(f"Reusing cached agent for user {user_id}")
        return cached_agent

    logger.info(f"Creating new agent for user {user_id}")
    
    try:
        # Use cached base config
        base = _get_base_config()
        logger.debug(f"Base config loaded: {base}")

        # Ensure meta-ads exists and set env
        if "mcpServers" not in base:
            base["mcpServers"] = {}
        base["mcpServers"]["meta-ads"] = base["mcpServers"].get("meta-ads", {})
        base["mcpServers"]["meta-ads"]["env"] = base["mcpServers"]["meta-ads"].get("env", {})
        base["mcpServers"]["meta-ads"]["env"]["META_ACCESS_TOKEN"] = access_token

        # write a temporary config file - use shared temp file but with better error handling
        temp_cfg = "./mcp_temp.json"
        import json
        with open(temp_cfg, "w") as f:
            json.dump(base, f)
        
        logger.debug(f"Temp config written to {temp_cfg}")

        # Create client and agent
        logger.debug("Creating MCP client...")
        client = MCPClient.from_config_file(temp_cfg)
        
        logger.debug("Creating LLM...")
        # Gemini LLM (commented out)
        # llm = ChatGoogleGenerativeAI(
        #     model="gemini-2.5-flash",
        #     google_api_key=os.getenv("GOOGLE_API_KEY"),
        #     temperature=0.2,
        # )
        
        # Claude Haiku via AWS Bedrock
        llm = ChatBedrock(
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            model_kwargs={
                "temperature": 0.2,
                "max_tokens": 4000
            }
        )

        logger.debug("Creating MCP agent...")
        agent = MCPAgent(
            llm=llm,
            client=client,
            max_steps=15,
            memory_enabled=True,
        )

        # Cache for subsequent messages
        _AGENT_CACHE[user_id] = agent
        _ACCESS_TOKEN_CACHE[user_id] = access_token
        
        logger.info(f"Successfully created and cached agent for user {user_id}")
        return agent

    except Exception as e:
        logger.error(f"Error initializing agent for user {user_id}: {e}", exc_info=True)
        # Remove from cache on error
        _AGENT_CACHE.pop(user_id, None)
        _ACCESS_TOKEN_CACHE.pop(user_id, None)
        raise Exception(f"MCP agent failed to initialize: {str(e)}")


async def create_user_client(user_id: int, access_token: str) -> MCPClient:
    """
    Create (or reuse) an MCPClient configured for the user's Meta token.
    This is for direct tool calls without using the agent.
    """
    # Reuse existing client if token hasn't changed
    cached_client = _CLIENT_CACHE.get(user_id)
    cached_token = _ACCESS_TOKEN_CACHE.get(user_id)
    if cached_client is not None and cached_token == access_token:
        return cached_client

    # Use cached base config
    base = _get_base_config()

    # Ensure meta-ads exists and set env
    if "mcpServers" not in base:
        base["mcpServers"] = {}
    base["mcpServers"]["meta-ads"] = base["mcpServers"].get("meta-ads", {})
    base["mcpServers"]["meta-ads"]["env"] = base["mcpServers"]["meta-ads"].get("env", {})
    base["mcpServers"]["meta-ads"]["env"]["META_ACCESS_TOKEN"] = access_token

    # write a temporary config file
    temp_cfg = f"./mcp_temp_client_{user_id}.json"  # User-specific temp file
    import json
    with open(temp_cfg, "w") as f:
        json.dump(base, f)

    client = MCPClient.from_config_file(temp_cfg)

    # Cache for subsequent calls
    _CLIENT_CACHE[user_id] = client
    _ACCESS_TOKEN_CACHE[user_id] = access_token

    # Clean up temp file
    try:
        os.remove(temp_cfg)
    except:
        pass

    return client


# Pre-warm function to initialize agents in background
async def prewarm_user_agent(user_id: int, access_token: str):
    """
    Pre-warm agent creation in background to reduce first message latency.
    Call this after user login or integration setup.
    """
    try:
        await create_user_agent(user_id, access_token)
        logger.info(f"Pre-warmed agent for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to pre-warm agent for user {user_id}: {e}")


# Cleanup function to remove cached agents
def cleanup_user_cache(user_id: int):
    """Remove user from all caches."""
    _AGENT_CACHE.pop(user_id, None)
    _ACCESS_TOKEN_CACHE.pop(user_id, None)
    _CLIENT_CACHE.pop(user_id, None)
    
    # Cancel any ongoing initialization task
    if user_id in _AGENT_INITIALIZATION_TASKS:
        task = _AGENT_INITIALIZATION_TASKS[user_id]
        if not task.done():
            task.cancel()
        del _AGENT_INITIALIZATION_TASKS[user_id]
