import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db import engine

async def run_migration():
    print("Starting postgres migration...")
    async with engine.begin() as conn:
        try:
            # PostgreSQL command to add column if not exists
            print("Adding is_email_verified column to Users table...")
            await conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN DEFAULT FALSE'))
            
            print("Setting existing users to verified...")
            await conn.execute(text('UPDATE "Users" SET is_email_verified = TRUE'))
            
            print("Migration successful.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_migration())
