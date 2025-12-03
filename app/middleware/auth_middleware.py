from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f"Request headers: {request.headers}")  # Log headers

        if request.method == "OPTIONS":
            return await call_next(request)

        # These routes do NOT require auth
        public_paths = [
            "/openapi.json",
            "/docs",
            "/redoc",
            "/api/auth/signup",   # Exclude the signup route
            "/api/auth/login",    # Exclude the login route
            "/api/meta/oauth",    # Meta OAuth start & callback (no JWT available)
            "/favicon.ico",       # Static browser icon
        ]

        for path in public_paths:
            if request.url.path.startswith(path):
                return await call_next(request)

        # Get token from header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing Authorization header"}, status_code=401)

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("id") or payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token")

            # Store in request.state
            request.state.user_id = int(user_id)

        except JWTError:
            return JSONResponse({"error": "Invalid token"}, status_code=401)

        response = await call_next(request)
        return response
