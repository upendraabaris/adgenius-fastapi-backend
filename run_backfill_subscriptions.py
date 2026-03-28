"""
Migration: Backfill free_trial subscription for existing users who have none.
Run once: python run_backfill_subscriptions.py
"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def run():
    async with AsyncSessionLocal() as session:
        # Get all user IDs that don't have a subscription yet
        result = await session.execute(text("""
            SELECT id FROM "Users"
            WHERE id NOT IN (SELECT user_id FROM subscriptions)
        """))
        user_ids = [row[0] for row in result.fetchall()]

        if not user_ids:
            print("✅ All users already have subscriptions. Nothing to do.")
            return

        expires_at = datetime.utcnow() + timedelta(days=14)
        for user_id in user_ids:
            await session.execute(text("""
                INSERT INTO subscriptions (user_id, plan, status, amount, currency, starts_at, expires_at, created_at, updated_at)
                VALUES (:user_id, 'free_trial', 'active', 0, 'INR', now(), :expires_at, now(), now())
            """), {"user_id": user_id, "expires_at": expires_at})

        await session.commit()
        print(f"✅ Assigned free_trial to {len(user_ids)} existing user(s): {user_ids}")

    await engine.dispose()

asyncio.run(run())
