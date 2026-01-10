#!/usr/bin/env python3
"""
Script to manually verify ROI calculation for a specific campaign
"""
import asyncio
import httpx
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

async def test_roi_verification():
    """Test ROI calculation by fetching raw Meta API data"""
    
    # You'll need to replace these with actual values from your database
    ACCESS_TOKEN = "YOUR_META_ACCESS_TOKEN"  # Get from integrations table
    ACCOUNT_ID = "YOUR_AD_ACCOUNT_ID"        # Get from selected account
    CAMPAIGN_ID = "YOUR_CAMPAIGN_ID"         # Get specific campaign ID
    
    print("🔍 ROI Verification Test")
    print("=" * 50)
    
    # Step 1: Get Campaign Insights (same as your API does)
    async with httpx.AsyncClient() as client:
        try:
            # Fetch campaign insights for last 30 days
            insights_url = f"https://graph.facebook.com/v20.0/{CAMPAIGN_ID}/insights"
            insights_params = {
                "access_token": ACCESS_TOKEN,
                "fields": "spend,actions,action_values,impressions,clicks,reach",
                "date_preset": "last_30d",
                "level": "campaign"
            }
            
            print(f"📡 Fetching insights for campaign: {CAMPAIGN_ID}")
            insights_response = await client.get(insights_url, params=insights_params)
            insights_data = insights_response.json()
            
            print(f"✅ Raw API Response:")
            print(json.dumps(insights_data, indent=2))
            
            if "data" in insights_data and insights_data["data"]:
                insight = insights_data["data"][0]
                
                # Step 2: Extract spend
                spend = float(insight.get("spend", 0))
                print(f"\n💰 Spend: ₹{spend}")
                
                # Step 3: Calculate revenue from actions
                actions = insight.get("actions", []) or []
                action_values = insight.get("action_values", []) or []
                
                print(f"\n📊 Actions Data:")
                for action in actions:
                    print(f"   - {action.get('action_type')}: {action.get('value')} times")
                
                print(f"\n💵 Action Values Data:")
                revenue = 0
                for action_value in action_values:
                    action_type = action_value.get("action_type", "")
                    value = float(action_value.get("value", 0))
                    print(f"   - {action_type}: ₹{value}")
                    
                    # Only count purchase-related actions as revenue
                    if action_type in ["purchase", "add_payment_info", "complete_registration"]:
                        revenue += value
                        print(f"     ✅ Added to revenue: ₹{value}")
                
                print(f"\n📈 Revenue Calculation:")
                print(f"   Total Revenue: ₹{revenue}")
                
                # Step 4: Calculate ROI
                if spend == 0:
                    roi_percentage = "0%"
                    print(f"   ⚠️  No spend data, ROI = 0%")
                else:
                    roi = ((revenue - spend) / spend) * 100
                    sign = "+" if roi >= 0 else ""
                    roi_percentage = f"{sign}{roi:.0f}%"
                    
                    print(f"\n🧮 ROI Calculation:")
                    print(f"   Formula: ((Revenue - Spend) / Spend) × 100")
                    print(f"   Calculation: (({revenue} - {spend}) / {spend}) × 100")
                    print(f"   Result: {roi_percentage}")
                
                # Step 5: Performance category
                roi_num = float(roi_percentage.replace("+", "").replace("%", "").replace("-", ""))
                if roi_num > 50:
                    performance = "excellent"
                elif roi_num > 0:
                    performance = "good"
                elif roi_num > -10:
                    performance = "average"
                else:
                    performance = "poor"
                
                print(f"\n🎯 Performance Category: {performance}")
                
                return {
                    "campaign_id": CAMPAIGN_ID,
                    "spend": spend,
                    "revenue": revenue,
                    "roi": roi_percentage,
                    "performance": performance,
                    "raw_data": insight
                }
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

# Helper function to get actual values from your database
async def get_campaign_data_from_db():
    """Get actual campaign data from your database for testing"""
    print("📋 To run this test, you need:")
    print("1. Get ACCESS_TOKEN from integrations table")
    print("2. Get ACCOUNT_ID from selected_ad_account")  
    print("3. Get CAMPAIGN_ID from Meta Ads Manager")
    print("\nSQL Queries to get data:")
    print("SELECT access_token, selected_ad_account FROM integrations WHERE provider='meta';")

if __name__ == "__main__":
    print("🚀 Starting ROI Verification")
    asyncio.run(get_campaign_data_from_db())
    # Uncomment below line after adding actual values
    # asyncio.run(test_roi_verification())