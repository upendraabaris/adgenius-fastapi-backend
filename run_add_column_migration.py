"""
Script to add selected_account_name column to integrations table
Run this: python run_add_column_migration.py
"""
import asyncio
from sqlalchemy import text
from app.db import AsyncSessionLocal

async def add_column():
    async with AsyncSessionLocal() as session:
        try:
            # Add column if not exists
            await session.execute(text("""
                ALTER TABLE integrations 
                ADD COLUMN IF NOT EXISTS selected_account_name TEXT;
            """))
            await session.commit()
            print("✅ Column 'selected_account_name' added successfully!")
            
            # Verify
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'integrations' 
                AND column_name = 'selected_account_name';
            """))
            row = result.fetchone()
            if row:
                print(f"✅ Verified: Column exists - {row[0]} ({row[1]})")
            else:
                print("❌ Column not found after adding!")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()

if __name__ == "__main__":
    print("🔧 Adding selected_account_name column to integrations table...")
    asyncio.run(add_column())
    print("✅ Migration complete!")
