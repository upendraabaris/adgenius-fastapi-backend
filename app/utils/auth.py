from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from app import models

def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return int(user_id)


async def _require_active_subscription(db: AsyncSession, user_id: int):
    """Ensure the user has an active subscription."""
    result = await db.execute(
        select(models.Subscription)
        .where(models.Subscription.user_id == user_id)
        .order_by(models.Subscription.created_at.desc())
    )
    sub = result.scalars().first()

    if sub and sub.status == "active" and sub.expires_at:
        # Check for expiry
        expires_at_naive = sub.expires_at.replace(tzinfo=None) if sub.expires_at.tzinfo else sub.expires_at
        if expires_at_naive < datetime.utcnow():
            sub.status = "expired"
            await db.commit()
            await db.refresh(sub)

    if not sub or sub.status != "active":
        raise HTTPException(
            status_code=402, 
            detail="Active subscription required. Please upgrade your plan."
        )
    return sub


async def _get_user_subscription(db: AsyncSession, user_id: int):
    """Simple helper to get subscription without raising 402 if not active (returns None or sub)."""
    result = await db.execute(
        select(models.Subscription)
        .where(models.Subscription.user_id == user_id)
        .order_by(models.Subscription.created_at.desc())
    )
    sub = result.scalars().first()
    return sub
