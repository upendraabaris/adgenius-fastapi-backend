import os
from fastapi import FastAPI
from dotenv import load_dotenv
load_dotenv()

from app.db import init_db
from app.routes import auth, business, integrations, chat, dashboard
from fastapi.middleware.cors import CORSMiddleware  # Import CORSMiddleware
from app.middleware.auth_middleware import AuthMiddleware  # Import AuthMiddleware
from app.routes import meta_oauth, oauth_status, settings

app = FastAPI(title="GrowCommerce FastAPI MCP")

frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "growcommerce.platinum-infotech.com,http://localhost:5176"
).split(",")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Add AuthMiddleware
app.add_middleware(AuthMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(business.router, prefix="/api/business", tags=["business"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(meta_oauth.router)
app.include_router(oauth_status.router)
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(settings.router)

@app.on_event("startup")
async def startup():
    await init_db()
    
    # Pre-load MCP config to avoid first-request delay
    try:
        from app.mcp_utils import _get_base_config
        config = _get_base_config()  # This will cache the base config
        print(f"✅ MCP config pre-loaded: {list(config.get('mcpServers', {}).keys())}")
    except Exception as e:
        print(f"⚠️ MCP config pre-load failed: {e}")

@app.get("/")
async def root():
    return {"ok": True, "msg": "GrowCommerce FastAPI MCP scaffold"}
