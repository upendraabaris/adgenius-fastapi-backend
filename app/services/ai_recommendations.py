import os
import json
import logging
from typing import List, Dict, Optional
from langchain_aws import ChatBedrock

logger = logging.getLogger(__name__)

def get_ai_llm():
    """Get Claude Haiku LLM instance."""
    return ChatBedrock(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        model_kwargs={
            "temperature": 0.2,
            "max_tokens": 4000
        }
    )

async def generate_ai_recommendations(
    campaigns_data: List[Dict],
    account_insights: Dict,
    campaign_insights: List[Dict],
    business_objective: Optional[str] = None,
    account_id: Optional[str] = None
) -> List[Dict]:
    """
    Generate AI-powered recommendations using Claude Haiku.
    
    Returns recommendations with ROI impact estimates and actionable insights.
    """
    try:
        llm = get_ai_llm()
        
        # Prepare data summary for AI analysis
        data_summary = {
            "account_performance": {
                "total_spend": account_insights.get("spend", 0),
                "total_impressions": account_insights.get("impressions", 0),
                "total_clicks": account_insights.get("clicks", 0),
                "account_ctr": account_insights.get("ctr", 0),
                "account_cpc": account_insights.get("cpc", 0),
            },
            "campaigns": [],
            "business_objective": business_objective or "Not specified"
        }
        
        # Process campaign data with insights
        insights_lookup = {}
        for insight in campaign_insights:
            campaign_id = insight.get("campaign_id")
            if campaign_id:
                insights_lookup[campaign_id] = insight
        
        for campaign in campaigns_data[:10]:  # Limit to top 10 campaigns
            campaign_id = campaign.get("id")
            insight = insights_lookup.get(campaign_id, {})
            
            spend = float(insight.get("spend", 0))
            impressions = int(insight.get("impressions", 0))
            clicks = int(insight.get("clicks", 0))
            
            # Calculate revenue from actions
            revenue = 0.0
            conversions = 0
            action_values = insight.get("action_values", []) or []
            actions = insight.get("actions", []) or []
            
            for action_value in action_values:
                action_type = action_value.get("action_type", "")
                value = float(action_value.get("value", 0) or 0)
                if "purchase" in action_type.lower():
                    revenue += value
            
            for action in actions:
                action_type = action.get("action_type", "")
                value = int(action.get("value", 0) or 0)
                if "purchase" in action_type.lower() or "conversion" in action_type.lower():
                    conversions += value
            
            roi = ((revenue - spend) / spend * 100) if spend > 0 else 0
            ctr = (clicks / impressions * 100) if impressions > 0 else 0
            
            data_summary["campaigns"].append({
                "name": campaign.get("name", "Unnamed"),
                "status": campaign.get("status", "UNKNOWN"),
                "objective": campaign.get("objective", "UNKNOWN"),
                "spend": spend,
                "revenue": revenue,
                "roi": roi,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "conversions": conversions
            })
        
        # Create AI prompt
        prompt = f"""
You are an expert Meta Ads consultant. Analyze the following campaign data and provide exactly 3 actionable recommendations.

ACCOUNT DATA:
{json.dumps(data_summary, indent=2)}

REQUIREMENTS:
1. Provide specific, data-driven recommendations
2. Include ROI impact estimates (be realistic based on current performance)
3. Focus on the most impactful optimizations
4. Consider the business objective: {business_objective or 'general performance'}

RESPONSE FORMAT (JSON only, no explanation):
[
  {{
    "title": "Specific recommendation title",
    "description": "Detailed explanation with current metrics",
    "campaign": "Campaign name or 'All Campaigns'",
    "action": "specific_action_type",
    "current_roi": "X%",
    "projected_roi": "Y%",
    "impact": "Estimated impact description",
    "confidence": "high/medium/low",
    "timeframe": "Expected timeframe for results"
  }}
]

Focus on:
- Budget reallocation for high-performing campaigns
- Pausing or optimizing underperforming campaigns  
- Audience and targeting improvements
- Creative optimization opportunities
- Bidding strategy adjustments

Provide realistic ROI projections based on current performance data.
"""

        # Get AI response
        response = await llm.ainvoke(prompt)
        ai_content = response.content
        
        # Parse AI response
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', ai_content, re.DOTALL)
            if json_match:
                ai_recommendations = json.loads(json_match.group())
            else:
                ai_recommendations = json.loads(ai_content)
            
            # Format recommendations for dashboard
            formatted_recommendations = []
            for i, rec in enumerate(ai_recommendations[:3], 1):
                formatted_recommendations.append({
                    "id": i,
                    "title": rec.get("title", "AI Recommendation"),
                    "description": rec.get("description", "AI-generated recommendation"),
                    "status": "pending",
                    "campaign": rec.get("campaign", "All Campaigns"),
                    "action": rec.get("action", "optimize"),
                    "impact": rec.get("impact", "Performance improvement expected"),
                    "ai_insights": {
                        "current_roi": rec.get("current_roi", "N/A"),
                        "projected_roi": rec.get("projected_roi", "N/A"),
                        "confidence": rec.get("confidence", "medium"),
                        "timeframe": rec.get("timeframe", "2-4 weeks")
                    }
                })
            
            return formatted_recommendations
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI recommendations JSON: {e}")
            logger.error(f"AI Response: {ai_content}")
            return _get_fallback_recommendations()
            
    except Exception as e:
        logger.error(f"Error generating AI recommendations: {e}")
        return _get_fallback_recommendations()

def _get_fallback_recommendations() -> List[Dict]:
    """Fallback recommendations when AI fails."""
    return [
        {
            "id": 1,
            "title": "Review Campaign Performance",
            "description": "AI analysis temporarily unavailable. Review your top-performing campaigns and consider budget reallocation.",
            "status": "pending",
            "campaign": "All Campaigns",
            "action": "manual_review",
            "impact": "Maintain optimal performance",
            "ai_insights": {
                "current_roi": "N/A",
                "projected_roi": "N/A", 
                "confidence": "medium",
                "timeframe": "Immediate"
            }
        }
    ]

async def get_campaign_optimization_suggestions(campaign_data: Dict, insight_data: Dict) -> Dict:
    """
    Get specific optimization suggestions for a single campaign using AI.
    """
    try:
        llm = get_ai_llm()
        
        prompt = f"""
Analyze this Meta Ads campaign and provide optimization suggestions:

CAMPAIGN: {json.dumps(campaign_data, indent=2)}
PERFORMANCE: {json.dumps(insight_data, indent=2)}

Provide specific optimization suggestions in JSON format:
{{
  "budget_recommendation": "increase/decrease/maintain with reasoning",
  "targeting_suggestions": ["specific targeting improvements"],
  "creative_recommendations": ["creative optimization ideas"],
  "bidding_strategy": "recommended bidding approach",
  "roi_projection": "realistic ROI improvement estimate"
}}
"""
        
        response = await llm.ainvoke(prompt)
        return json.loads(response.content)
        
    except Exception as e:
        logger.error(f"Error getting campaign optimization: {e}")
        return {
            "budget_recommendation": "Review performance metrics",
            "targeting_suggestions": ["Analyze audience insights"],
            "creative_recommendations": ["Test new ad formats"],
            "bidding_strategy": "Monitor current strategy",
            "roi_projection": "Data analysis needed"
        }