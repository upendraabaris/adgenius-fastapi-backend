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
    if not integration:
        raise HTTPException(status_code=400, detail="No Meta integration found for user")
    if not integration.selected_ad_account:
        raise HTTPException(status_code=400, detail="No ad account selected for this user")

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
