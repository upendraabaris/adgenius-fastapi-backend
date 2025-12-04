import os
from fastapi import FastAPI
from dotenv import load_dotenv
load_dotenv()

from app.db import init_db
from app.routes import auth, business, integrations, chat, dashboard
from fastapi.middleware.cors import CORSMiddleware  # Import CORSMiddleware
from app.middleware.auth_middleware import AuthMiddleware  # Import AuthMiddleware
from app.routes import meta_oauth, oauth_status, settings

app = FastAPI(title="AdGenius FastAPI MCP")

frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5176,
http://ec2-3-110-186-189.ap-south-1.compute.amazonaws.com:5176"
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

@app.get("/")
async def root():
    return {"ok": True, "msg": "AdGenius FastAPI MCP scaffold"}
