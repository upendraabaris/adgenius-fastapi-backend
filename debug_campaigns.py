#!/usr/bin/env python3
"""
Debug script to check campaigns data
"""
import asyncio
import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_campaigns():
    """Debug campaigns API call"""
    
    # You need to get these from your database
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # From integrations table
    ACCOUNT_ID = "YOUR_ACCOUNT_ID"      # From selected_ad_account
    
    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN":
        print("❌ Please update ACCESS_TOKEN and ACCOUNT_ID in this script")
        print("Run: python get_test_data.py to get the values")
        return
    
    async with httpx.AsyncClient() as client:
        try:
            # 1. Check campaigns
            campaigns_url = f"https://graph.facebook.com/v20.0/{ACCOUNT_ID}/campaigns"
            campaigns_params = {
                "access_token": ACCESS_TOKEN,
                "fields": "id,name,status,objective",
                "limit": 50
            }
            
            print("🔍 Fetching campaigns...")
            campaigns_response = await client.get(campaigns_url, params=campaigns_params)
            campaigns_data = campaigns_response.json()
            
            if "data" in campaigns_data:
                campaigns = campaigns_data["data"]
                print(f"✅ Found {len(campaigns)} campaigns:")
                
                for campaign in campaigns:
                    print(f"   • {campaign.get('name', 'Unnamed')}")
                    print(f"     ID: {campaign.get('id')}")
                    print(f"     Status: {campaign.get('status')}")
                    print(f"     Objective: {campaign.get('objective', 'N/A')}")
                    print()
                
                # Check how many are active
                active_campaigns = [c for c in campaigns if c.get('status') == 'ACTIVE']
                paused_campaigns = [c for c in campaigns if c.get('status') == 'PAUSED']
                
                print(f"📊 Campaign Status Summary:")
                print(f"   Active: {len(active_campaigns)}")
                print(f"   Paused: {len(paused_campaigns)}")
                print(f"   Other: {len(campaigns) - len(active_campaigns) - len(paused_campaigns)}")
                
            else:
                print(f"❌ No campaigns data: {campaigns_data}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_campaigns())