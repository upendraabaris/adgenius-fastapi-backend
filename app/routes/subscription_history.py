from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db import AsyncSessionLocal
from app.models import Subscription

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/api/subscription/history")
async def subscription_history(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return []
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    history = result.scalars().all()
    return [
        {
            "plan": sub.plan,
            "status": sub.status,
            "expires_at": sub.expires_at,
            "starts_at": sub.starts_at,
        } for sub in history
    ]
