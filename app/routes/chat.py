from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models
from app.mcp_utils import create_user_agent

router = APIRouter()


class ChatReq(BaseModel):
    message: str


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return int(user_id)


@router.post("/")
async def chat(
    req: ChatReq,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    # Load this user's Meta integration (must have selected_ad_account)
    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = result.scalars().first()

    # If user is not connected to any Meta account, return a friendly guidance message
    if not integration:
        guidance = (
            "It looks like you don't have a Meta Ads account connected yet. "
            "Please go to the Settings page, connect your Meta Ads account under "
            "\"Connected Accounts\", and then come back here to ask questions "
            "about your campaigns."
        )
        return {
            "success": False,
            "tool": None,
            "args": None,
            "result": None,
            "reply": guidance,
        }

    # If integration exists but no primary ad account is selected
    if not integration.selected_ad_account:
        guidance = (
            "You are connected to Meta, but no primary ad account is selected yet. "
            "Please open the Settings page, use the \"Select/Change Account\" option "
            "under Meta Ads in Connected Accounts, choose an ad account, and then "
            "return to this chat to ask about your performance."
        )
        return {
            "success": False,
            "tool": None,
            "args": None,
            "result": None,
            "reply": guidance,
        }

    access_token = integration.access_token
    ad_account_id = integration.selected_ad_account

    # Build or reuse user-specific MCP agent (cached per user_id)
    agent = await create_user_agent(user_id, access_token)

    # Give the agent explicit context about which ad account to use
    prompt = (
        f"You are connected to Meta Ads for this user. "
        f"The primary ad account id to use is: {ad_account_id}. "
        f"Answer the following question using that account where relevant:\n\n{req.message}"
    )

    out = await agent.run(prompt)

    # Normalized chat response shape expected by frontend
    return {
        "success": True,
        "tool": None,
        "args": None,
        "result": None,
        "reply": out,
    }
