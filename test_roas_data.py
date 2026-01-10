#!/usr/bin/env python3
"""
Test ROAS data from Meta API
"""
import asyncio
import httpx
import json

async def test_roas_data():
    """Test ROAS data from Meta API"""
    
    # You need to get these from your database
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # From integrations table
    ACCOUNT_ID = "YOUR_ACCOUNT_ID"      # From selected_ad_account
    
    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN":
        print("❌ Please update ACCESS_TOKEN and ACCOUNT_ID in this script")
        print("Run: python get_test_data.py to get the values")
        return
    
    if not ACCOUNT_ID.startswith('act_'):
        ACCOUNT_ID = f'act_{ACCOUNT_ID}'
    
    async with httpx.AsyncClient() as client:
        try:
            print("🔍 Testing ROAS data from Meta API...")
            
            # Test campaign insights with purchase_roas
            print("\n1. Testing campaign insights with purchase_roas...")
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{ACCOUNT_ID}/insights",
                params={
                    "access_token": ACCESS_TOKEN,
                    "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions,action_values,purchase_roas",
                    "date_preset": "last_30d",
                    "level": "campaign"
                },
            )
            resp.raise_for_status()
            data = resp.json()
            
            campaigns = data.get("data", [])
            print(f"   ✅ Found {len(campaigns)} campaigns with insights")
            
            for i, campaign in enumerate(campaigns[:3]):  # Show first 3
                print(f"\n   📊 Campaign {i+1}: {campaign.get('campaign_name', 'Unnamed')}")
                print(f"      Campaign ID: {campaign.get('campaign_id')}")
                print(f"      Spend: ${campaign.get('spend', 0)}")
                print(f"      Impressions: {campaign.get('impressions', 0)}")
                
                # Check purchase_roas
                purchase_roas = campaign.get('purchase_roas', [])
                if purchase_roas:
                    roas_value = purchase_roas[0].get('value', 0)
                    print(f"      ✅ Purchase ROAS: {roas_value}x (from Meta API)")
                else:
                    print(f"      ❌ No purchase_roas data")
                
                # Check action_values for manual calculation
                action_values = campaign.get('action_values', [])
                if action_values:
                    print(f"      📈 Action Values:")
                    revenue = 0
                    for av in action_values:
                        action_type = av.get('action_type', '')
                        value = float(av.get('value', 0))
                        print(f"         - {action_type}: ${value}")
                        if 'purchase' in action_type.lower():
                            revenue += value
                    
                    spend = float(campaign.get('spend', 0))
                    if spend > 0:
                        manual_roas = revenue / spend
                        print(f"      🧮 Manual ROAS: {manual_roas:.2f}x (calculated)")
                else:
                    print(f"      ❌ No action_values data")
            
            # Summary
            campaigns_with_roas = [c for c in campaigns if c.get('purchase_roas')]
            campaigns_with_actions = [c for c in campaigns if c.get('action_values')]
            
            print(f"\n📋 Summary:")
            print(f"   Total campaigns: {len(campaigns)}")
            print(f"   Campaigns with purchase_roas: {len(campaigns_with_roas)}")
            print(f"   Campaigns with action_values: {len(campaigns_with_actions)}")
            
            if len(campaigns_with_roas) == 0 and len(campaigns_with_actions) == 0:
                print(f"   ⚠️  No ROAS or revenue data found!")
                print(f"   This might be because:")
                print(f"   - No purchase events are being tracked")
                print(f"   - Meta Pixel is not properly configured")
                print(f"   - No conversions have occurred in the last 30 days")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_roas_data())