#!/usr/bin/env python3
"""
Test campaigns API directly
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services import meta_service

async def test_campaigns_api():
    """Test campaigns API calls"""
    
    # You need to get these from your database
    USER_ID = 1  # Replace with actual user ID
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # From integrations table
    ACCOUNT_ID = "YOUR_ACCOUNT_ID"      # From selected_ad_account
    
    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN":
        print("❌ Please update ACCESS_TOKEN and ACCOUNT_ID in this script")
        print("Run: python get_test_data.py to get the values")
        return
    
    try:
        print("🔍 Testing Meta Service API calls...")
        
        # Test 1: Get campaigns
        print("\n1. Testing get_campaigns...")
        campaigns = await meta_service.get_campaigns(USER_ID, ACCESS_TOKEN, ACCOUNT_ID)
        print(f"   ✅ Found {len(campaigns)} campaigns")
        
        for i, campaign in enumerate(campaigns[:3]):  # Show first 3
            print(f"   • Campaign {i+1}: {campaign.get('name', 'Unnamed')}")
            print(f"     ID: {campaign.get('id')}")
            print(f"     Status: {campaign.get('status')}")
        
        # Test 2: Get campaign insights
        print("\n2. Testing get_campaign_insights...")
        insights = await meta_service.get_campaign_insights(USER_ID, ACCESS_TOKEN, ACCOUNT_ID)
        print(f"   ✅ Found {len(insights)} campaign insights")
        
        # Test 3: Get campaign budgets
        print("\n3. Testing get_campaign_budgets...")
        budgets = await meta_service.get_campaign_budgets(USER_ID, ACCESS_TOKEN, ACCOUNT_ID)
        print(f"   ✅ Found {len(budgets)} campaign budgets")
        
        # Test 4: Check active campaigns
        active_campaigns = [c for c in campaigns if c.get('status') == 'ACTIVE']
        print(f"\n📊 Active Campaigns: {len(active_campaigns)}")
        
        if active_campaigns:
            print("   Active campaign names:")
            for campaign in active_campaigns:
                print(f"   • {campaign.get('name', 'Unnamed')}")
        else:
            print("   ❌ No ACTIVE campaigns found!")
            print("   All campaign statuses:")
            for campaign in campaigns:
                print(f"   • {campaign.get('name', 'Unnamed')}: {campaign.get('status')}")
        
        return {
            "campaigns": len(campaigns),
            "insights": len(insights),
            "budgets": len(budgets),
            "active_campaigns": len(active_campaigns)
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_campaigns_api())
    if result:
        print(f"\n✅ Test completed successfully: {result}")
    else:
        print(f"\n❌ Test failed")