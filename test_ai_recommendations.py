#!/usr/bin/env python3
"""
Test AI recommendations for campaigns
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.routes.dashboard import _get_campaign_optimization_recommendation

async def test_ai_recommendations():
    """Test AI recommendations with sample campaign data"""
    
    # Sample campaign data for testing
    test_campaigns = [
        {
            "campaign_data": {
                "name": "Summer Sale Campaign",
                "status": "ACTIVE",
                "objective": "CONVERSIONS"
            },
            "insight_data": {
                "spend": 1000,
                "impressions": 50000,
                "clicks": 750,
                "reach": 35000,
                "purchase_roas": [{"value": "2.5"}],
                "actions": [{"action_type": "purchase", "value": "15"}]
            },
            "business_objective": "Increase online sales"
        },
        {
            "campaign_data": {
                "name": "Brand Awareness Campaign",
                "status": "ACTIVE", 
                "objective": "REACH"
            },
            "insight_data": {
                "spend": 500,
                "impressions": 100000,
                "clicks": 200,
                "reach": 80000,
                "purchase_roas": [{"value": "0.8"}],
                "actions": [{"action_type": "purchase", "value": "3"}]
            },
            "business_objective": "Build brand awareness"
        },
        {
            "campaign_data": {
                "name": "High Performance Campaign",
                "status": "ACTIVE",
                "objective": "CONVERSIONS"
            },
            "insight_data": {
                "spend": 2000,
                "impressions": 80000,
                "clicks": 2400,
                "reach": 60000,
                "purchase_roas": [{"value": "4.2"}],
                "actions": [{"action_type": "purchase", "value": "45"}]
            },
            "business_objective": "Maximize revenue"
        }
    ]
    
    print("🤖 Testing AI Campaign Optimization Recommendations")
    print("=" * 60)
    
    for i, test_case in enumerate(test_campaigns, 1):
        print(f"\n📊 Test Case {i}: {test_case['campaign_data']['name']}")
        print(f"   ROAS: {test_case['insight_data']['purchase_roas'][0]['value']}x")
        print(f"   Spend: ${test_case['insight_data']['spend']}")
        print(f"   Clicks: {test_case['insight_data']['clicks']:,}")
        
        try:
            recommendations = await _get_campaign_optimization_recommendation(
                campaign_data=test_case['campaign_data'],
                insight_data=test_case['insight_data'],
                business_objective=test_case['business_objective']
            )
            
            print(f"   🎯 AI Recommendations ({len(recommendations)} tips):")
            for j, rec in enumerate(recommendations, 1):
                print(f"      {j}. {rec}")
            print(f"   ✅ Success")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n🏁 AI Recommendations Test Completed")

if __name__ == "__main__":
    asyncio.run(test_ai_recommendations())