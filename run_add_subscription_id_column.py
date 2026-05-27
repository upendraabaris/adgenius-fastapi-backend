"""
Migration: Add razorpay_subscription_id column to subscriptions table
Run: python run_add_subscription_id_column.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def run():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[Error] DATABASE_URL not found in environment!")
        return

    print("Connecting to database and applying migration...")
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE "subscriptions"
            ADD COLUMN IF NOT EXISTS razorpay_subscription_id VARCHAR(255);
        """))
    print("Migration applied successfully: razorpay_subscription_id column added!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run())
