import asyncio
from datetime import datetime
from app.db import AsyncSessionLocal
from app.models import Subscription

async def expire_subscriptions():
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        result = await session.execute(
            Subscription.__table__.update()
            .where(Subscription.status == "active")
            .where(Subscription.expires_at != None)
            .where(Subscription.expires_at < now)
            .values(status="expired")
        )
        await session.commit()
        print("Expired subscriptions updated.")

if __name__ == "__main__":
    asyncio.run(expire_subscriptions())
