"""
Script to add email_otp and email_otp_expires_at columns to Users table
Run this: python run_add_otp_columns.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db import AsyncSessionLocal

async def add_columns():
    async with AsyncSessionLocal() as session:
        try:
            # Add columns if not exists
            await session.execute(text("""
                ALTER TABLE "Users" 
                ADD COLUMN IF NOT EXISTS email_otp VARCHAR(10),
                ADD COLUMN IF NOT EXISTS email_otp_expires_at TIMESTAMP WITH TIME ZONE;
            """))
            await session.commit()
            print("[OK] Columns 'email_otp' and 'email_otp_expires_at' added successfully!")
            
            # Verify
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'Users' 
                AND column_name IN ('email_otp', 'email_otp_expires_at');
            """))
            rows = result.fetchall()
            if rows:
                for row in rows:
                    print(f"[OK] Verified: Column exists - {row[0]} ({row[1]})")
            else:
                print("[ERROR] Columns not found after adding!")
                
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            await session.rollback()

if __name__ == "__main__":
    print("[INFO] Adding OTP columns to Users table...")
    asyncio.run(add_columns())
    print("[OK] Migration complete!")
