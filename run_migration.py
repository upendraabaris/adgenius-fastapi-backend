#!/usr/bin/env python3
"""
Simple script to run the database migration for adding selected_account_name column
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_migration():
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return
    
    # Parse the URL to get connection parameters
    # DATABASE_URL format: postgresql+asyncpg://user:password@host:port/database
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(url)
        print("✅ Connected to database")
        
        # Check if column already exists
        check_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'integrations' 
        AND column_name = 'selected_account_name';
        """
        
        result = await conn.fetch(check_query)
        
        if result:
            print("✅ Column 'selected_account_name' already exists")
        else:
            # Add the column
            migration_query = "ALTER TABLE integrations ADD COLUMN selected_account_name TEXT;"
            await conn.execute(migration_query)
            print("✅ Successfully added 'selected_account_name' column to integrations table")
        
        await conn.close()
        print("✅ Migration completed successfully")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_migration())