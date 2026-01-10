#!/usr/bin/env python3
"""
Get test data from database for ROI verification
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def get_test_data():
    """Get access token and account ID from database"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not found")
        return
    
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        conn = await asyncpg.connect(url)
        print("✅ Connected to database")
        
        # Get integration data
        query = """
        SELECT 
            access_token, 
            selected_ad_account, 
            selected_account_name,
            ad_accounts
        FROM integrations 
        WHERE provider = 'meta' 
        AND access_token IS NOT NULL
        LIMIT 1;
        """
        
        result = await conn.fetchrow(query)
        
        if result:
            print(f"\n📋 Test Data:")
            print(f"Access Token: {result['access_token'][:20]}...")
            print(f"Selected Account: {result['selected_ad_account']}")
            print(f"Account Name: {result['selected_account_name']}")
            
            # Show available ad accounts
            if result['ad_accounts']:
                print(f"\n📊 Available Ad Accounts:")
                for account in result['ad_accounts']:
                    print(f"   - ID: {account.get('id')}")
                    print(f"     Name: {account.get('name', 'N/A')}")
                    print(f"     Currency: {account.get('currency', 'N/A')}")
            
            print(f"\n🔧 Update test_roi_verification.py with:")
            print(f"ACCESS_TOKEN = '{result['access_token']}'")
            print(f"ACCOUNT_ID = '{result['selected_ad_account']}'")
            
        else:
            print("❌ No Meta integration found in database")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_test_data())