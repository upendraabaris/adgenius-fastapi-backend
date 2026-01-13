from datetime import datetime
from typing import Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models, schemas
from app.services import meta_service

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


def _format_currency(amount: float, currency: str = "INR") -> str:
    """Format amount as currency string based on currency type."""
    if currency == "INR":
        if amount >= 100000:  # 1 Lakh+
            return f"₹{amount/100000:.1f}L"
        elif amount >= 1000:  # 1K+
            return f"₹{amount/1000:.1f}K"
        else:
            return f"₹{amount:,.0f}"
    elif currency == "USD":
        if amount >= 1000:
            return f"${amount:,.0f}"
        return f"${amount:,.2f}"
    else:
        # Generic formatting for other currencies
        if amount >= 1000:
            return f"{amount:,.0f} {currency}"
        return f"{amount:,.2f} {currency}"


async def _get_account_currency(user_id: int, access_token: str, account_id: str) -> str:
    """Get the currency of the ad account."""
    try:
        # Ensure account_id has 'act_' prefix
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{account_id}",
                params={
                    "access_token": access_token,
                    "fields": "currency,account_id,name",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("currency", "USD")
    except Exception as e:
        print(f"Error fetching account currency: {e}")
        return "USD"  # Default fallback


def _format_number(num: int | float) -> str:
    """Format number with commas."""
    return f"{int(num):,}"


async def _get_account_currency(user_id: int, access_token: str, account_id: str) -> str:
    """Get the currency of the ad account."""
    try:
        # Ensure account_id has 'act_' prefix
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{account_id}",
                params={
                    "access_token": access_token,
                    "fields": "currency,account_id,name",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("currency", "USD")
    except Exception as e:
        print(f"Error fetching account currency: {e}")
def _calculate_roi(spend: float, revenue: float) -> str:
    """Calculate ROI percentage."""
    if spend == 0:
        return "0%"
    roi = ((revenue - spend) / spend) * 100
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.0f}%"


def _calculate_roas(spend: float, revenue: float) -> str:
    """Calculate ROAS (Return on Ad Spend) ratio."""
    if spend == 0:
        return "0.00x"
    roas = revenue / spend
    return f"{roas:.2f}x"


async def _get_campaign_optimization_recommendation(campaign_data: Dict, insight_data: Dict, business_objective: Optional[str] = None) -> List[str]:
    """
    Generate AI-powered optimization recommendations for a single campaign using Claude Haiku.
    Returns a list of 3-4 specific optimization tips based on campaign's unique performance.
    """
    try:
        from app.services.ai_recommendations import get_ai_llm
        
        llm = get_ai_llm()
        
        # Extract key metrics
        spend = float(insight_data.get("spend", 0))
        impressions = int(insight_data.get("impressions", 0))
        clicks = int(insight_data.get("clicks", 0))
        reach = int(insight_data.get("reach", 0))
        
        # Get ROAS
        roas_data = insight_data.get("purchase_roas", [])
        roas = float(roas_data[0].get("value", 0)) if roas_data else 0
        
        # Calculate CTR and other metrics
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        cpc = (spend / clicks) if clicks > 0 else 0
        frequency = float(insight_data.get("frequency", 0))
        
        # Get conversions and revenue
        actions = insight_data.get("actions", []) or []
        action_values = insight_data.get("action_values", []) or []
        conversions = 0
        revenue = 0.0
        
        for action in actions:
            if "purchase" in action.get("action_type", "").lower():
                conversions += int(action.get("value", 0))
        
        for action_value in action_values:
            if "purchase" in action_value.get("action_type", "").lower():
                revenue += float(action_value.get("value", 0))
        
        # Calculate additional metrics
        conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0
        cost_per_conversion = (spend / conversions) if conversions > 0 else 0
        
        # Determine performance issues and strengths
        performance_analysis = []
        if roas < 1.0:
            performance_analysis.append("LOW_ROAS")
        elif roas > 3.0:
            performance_analysis.append("HIGH_ROAS")
        
        if ctr < 1.0:
            performance_analysis.append("LOW_CTR")
        elif ctr > 3.0:
            performance_analysis.append("HIGH_CTR")
        
        if cpc > 2.0:
            performance_analysis.append("HIGH_CPC")
        elif cpc < 0.5:
            performance_analysis.append("LOW_CPC")
        
        if frequency > 3.0:
            performance_analysis.append("HIGH_FREQUENCY")
        elif frequency < 1.5:
            performance_analysis.append("LOW_FREQUENCY")
        
        if conversion_rate < 1.0:
            performance_analysis.append("LOW_CONVERSION_RATE")
        elif conversion_rate > 5.0:
            performance_analysis.append("HIGH_CONVERSION_RATE")

        prompt = f"""
You are a Meta Ads expert analyzing campaign "{campaign_data.get('name', 'Unnamed')}". 

CAMPAIGN DETAILS:
- Name: {campaign_data.get('name', 'Unnamed')}
- Objective: {campaign_data.get('objective', 'Unknown')}
- Business Goal: {business_objective or 'Not specified'}

CURRENT PERFORMANCE:
- Spend: ₹{spend:.2f}
- ROAS: {roas:.2f}x
- Revenue: ₹{revenue:.2f}
- Impressions: {impressions:,}
- Clicks: {clicks:,}
- CTR: {ctr:.2f}%
- CPC: ₹{cpc:.2f}
- Conversions: {conversions}
- Conversion Rate: {conversion_rate:.2f}%
- Cost per Conversion: ₹{cost_per_conversion:.2f}
- Reach: {reach:,}
- Frequency: {frequency:.2f}

PERFORMANCE ISSUES DETECTED: {', '.join(performance_analysis) if performance_analysis else 'None'}

Based on THIS SPECIFIC CAMPAIGN'S performance data, provide exactly 3-4 unique optimization recommendations. Each recommendation must be:
1. Specific to this campaign's actual metrics
2. Actionable and measurable
3. Different from generic advice
4. Max 75 characters each

RESPONSE FORMAT (JSON array only):
[
  "Specific recommendation based on actual metrics",
  "Another unique recommendation for this campaign",
  "Third specific optimization tip",
  "Fourth targeted improvement suggestion"
]

EXAMPLES OF SPECIFIC RECOMMENDATIONS:
- If ROAS is 0.8x: "Pause campaign and analyze why ROAS is 20% below break-even"
- If CTR is 0.5%: "Replace ad creative - current CTR of 0.5% is 3x below benchmark"
- If CPC is ₹3.50: "Refine targeting to reduce ₹3.50 CPC which is 75% above optimal"
- If frequency is 4.2: "Expand audience - current 4.2 frequency indicates ad fatigue"
- If conversion rate is 0.3%: "Optimize landing page - 0.3% conversion rate needs improvement"

Focus on the WORST performing metrics first, then suggest improvements for the best opportunities.

Return only the JSON array, no explanations.
"""

        response = await llm.ainvoke(prompt)
        ai_content = response.content.strip()
        
        # Parse AI response
        try:
            import json
            import re
            
            # Extract JSON array from response
            json_match = re.search(r'\[.*\]', ai_content, re.DOTALL)
            if json_match:
                recommendations = json.loads(json_match.group())
            else:
                recommendations = json.loads(ai_content)
            
            # Ensure we have a list and limit to 4 items
            if isinstance(recommendations, list) and len(recommendations) > 0:
                return recommendations[:4]
            else:
                raise ValueError("AI response is not a valid list")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse AI recommendations: {e}")
            logger.error(f"AI Response: {ai_content}")
            # Fall through to fallback logic
        
    except Exception as e:
        logger.error(f"Error generating AI recommendations: {e}")
    
    # Enhanced fallback recommendations based on specific metrics
    fallback_recommendations = []
    
    # ROAS-specific recommendations
    if roas < 0.5:
        fallback_recommendations.append(f"Critical: ROAS {roas:.2f}x is severely low - pause and review targeting")
        fallback_recommendations.append(f"Analyze why ₹{spend:.0f} spend generated only ₹{revenue:.0f} revenue")
    elif roas < 1.0:
        fallback_recommendations.append(f"ROAS {roas:.2f}x below break-even - optimize targeting immediately")
        fallback_recommendations.append(f"Test new creatives to improve {conversions} conversions from ₹{spend:.0f}")
    elif roas < 2.0:
        fallback_recommendations.append(f"ROAS {roas:.2f}x is profitable - test 20% budget increase")
        fallback_recommendations.append(f"Scale from ₹{spend:.0f} to ₹{spend*1.2:.0f} daily to maximize returns")
    elif roas >= 3.0:
        fallback_recommendations.append(f"Excellent {roas:.2f}x ROAS - increase budget by 50% immediately")
        fallback_recommendations.append(f"Scale this ₹{spend:.0f}/day winner to ₹{spend*1.5:.0f}/day")
    
    # CTR-specific recommendations
    if ctr < 0.8:
        fallback_recommendations.append(f"CTR {ctr:.2f}% is critically low - replace ad creative urgently")
    elif ctr < 1.5:
        fallback_recommendations.append(f"Improve {ctr:.2f}% CTR with better headlines and visuals")
    elif ctr > 4.0:
        fallback_recommendations.append(f"Excellent {ctr:.2f}% CTR - focus on conversion optimization")
    
    # CPC-specific recommendations  
    if cpc > 3.0:
        fallback_recommendations.append(f"High ₹{cpc:.2f} CPC - refine audience to reduce costs")
    elif cpc < 0.5:
        fallback_recommendations.append(f"Low ₹{cpc:.2f} CPC indicates good targeting - scale budget")
    
    # Frequency-specific recommendations
    if frequency > 4.0:
        fallback_recommendations.append(f"Frequency {frequency:.1f} shows ad fatigue - expand audience size")
    elif frequency < 1.2:
        fallback_recommendations.append(f"Low {frequency:.1f} frequency - increase budget for more reach")
    
    # Conversion-specific recommendations
    if conversion_rate < 0.5:
        fallback_recommendations.append(f"Low {conversion_rate:.2f}% conversion rate - optimize landing page")
    elif conversions == 0:
        fallback_recommendations.append(f"Zero conversions from {clicks} clicks - check tracking setup")
    
    # Ensure we have at least 3 recommendations
    if len(fallback_recommendations) < 3:
        fallback_recommendations.extend([
            f"Monitor {campaign_data.get('name', 'campaign')} performance daily",
            f"Test new audiences for {campaign_data.get('objective', 'campaign')} objective",
            f"A/B test ad formats to improve {ctr:.1f}% CTR"
        ])
    
    return fallback_recommendations[:4]


async def _build_stats(
    meta_connected: bool,
    business_objective: str | None,
    user_id: Optional[int] = None,
    access_token: Optional[str] = None,
    account_id: Optional[str] = None,
) -> List[Dict]:
    """Build stats from actual Meta Ads data if available."""
    
    # Default values when Meta is not connected
    if not meta_connected or not access_token or not account_id or not user_id:
        spend_value = "₹0"
        campaigns_value = "0"
        impressions_value = "0"
        reach_value = "0"
        daily_budget_value = "₹0"
        roi_value = "0%"
        conversions_value = "0"
        spend_change = "0%"
        campaigns_change = "0"
        roi_change = "0%"
        conversions_change = "0%"
    else:
        try:
            # Get account currency first
            currency = await _get_account_currency(user_id, access_token, account_id)
            
            # Fetch actual insights using direct API with fallback
            insights = await meta_service.get_account_insights(user_id, access_token, account_id)
            campaigns_data = await meta_service.get_campaigns(user_id, access_token, account_id)
            
            # Calculate spend with proper currency
            spend = float(insights.get("spend", 0))
            spend_value = _format_currency(spend, currency)
            
            # Get impressions and reach
            impressions = int(insights.get("impressions", 0))
            impressions_value = _format_number(impressions)
            
            reach = int(insights.get("reach", 0))
            reach_value = _format_number(reach)
            
            # Count ONLY ACTIVE campaigns
            active_campaigns = [c for c in campaigns_data if c.get("status", "").upper() == "ACTIVE"]
            campaigns_value = str(len(active_campaigns))
            
            # Get campaign budgets for daily budget calculation - ONLY ACTIVE campaigns
            campaign_budgets = await meta_service.get_campaign_budgets(user_id, access_token, account_id)
            total_daily_budget = 0
            active_campaign_ids = [c.get("id") for c in active_campaigns]
            
            for budget_info in campaign_budgets:
                campaign_id = budget_info.get("campaign_id")
                # Only include budget if campaign is active
                if campaign_id in active_campaign_ids:
                    daily_budget = float(budget_info.get("daily_budget", 0) or 0)
                    # Convert from cents to currency units (Meta API returns in cents)
                    daily_budget = daily_budget / 100
                    total_daily_budget += daily_budget
            
            daily_budget_value = _format_currency(total_daily_budget, currency)
            
            # Calculate conversions and revenue
            actions = insights.get("actions", []) or []
            action_values = insights.get("action_values", []) or []
            conversions = 0
            revenue = 0.0
            
            # Extract conversion actions
            for action in actions:
                action_type = action.get("action_type", "")
                value = int(action.get("value", 0) or 0)
                if "purchase" in action_type.lower() or "conversion" in action_type.lower() or "lead" in action_type.lower():
                    conversions += value
            
            # Extract purchase values (revenue)
            for action_value in action_values:
                action_type = action_value.get("action_type", "")
                value = float(action_value.get("value", 0) or 0)
                if "purchase" in action_type.lower():
                    revenue += value
            
            conversions_value = _format_number(conversions)
            
            # Get ROAS from Meta API or calculate manually
            roas_data = insights.get("purchase_roas", [])
            if roas_data and len(roas_data) > 0:
                # Use Meta's calculated ROAS
                roas_num = float(roas_data[0].get("value", 0))
                roas_value = f"{roas_num:.2f}x"
            else:
                # Fallback: calculate ROAS manually
                roas_value = _calculate_roas(spend, revenue) if spend > 0 else "0.00x"
            
            # For changes, we'd need historical data - using placeholder for now
            # In production, you'd compare with previous period
            spend_change = "+0%"
            campaigns_change = "0"
            roi_change = "+0%"
            conversions_change = "+0%"
            
        except Exception as e:
            # Fallback to defaults if API call fails
            spend_value = "₹0"
            campaigns_value = "0"
            impressions_value = "0"
            reach_value = "0"
            daily_budget_value = "₹0"
            roas_value = "0.00x"
            conversions_value = "0"
            spend_change = "0%"
            campaigns_change = "0"
            conversions_change = "0%"

    return [
        {"id": "spend", "title": "Active Spend", "value": spend_value, "change": spend_change, "trend": "up" if spend_change.startswith("+") else "down"},
        {"id": "campaigns", "title": "Active Campaigns", "value": campaigns_value, "change": campaigns_change, "trend": "up" if campaigns_change.startswith("+") else "down"},
        {"id": "impressions", "title": "Impressions", "value": impressions_value, "change": "+0%", "trend": "up"},
        {"id": "reach", "title": "Reach", "value": reach_value, "change": "+0%", "trend": "up"},
        {"id": "daily_budget", "title": "Active Budget", "value": daily_budget_value, "change": "+0%", "trend": "neutral"},
        {"id": "roas", "title": "Avg. ROAS", "value": roas_value, "change": "+0%", "trend": "up"},
        {"id": "conversions", "title": "Conversions", "value": conversions_value, "change": conversions_change, "trend": "up" if conversions_change.startswith("+") else "down"},
    ]


async def _build_campaigns(
    meta_connected: bool,
    objective: str | None,
    user_id: Optional[int] = None,
    access_token: Optional[str] = None,
    account_id: Optional[str] = None,
) -> List[Dict]:
    """Build campaigns list from actual Meta Ads data if available."""
    
    if not meta_connected:
        return [
            {
                "name": "Connect Meta Ads",
                "status": "setup",
                "spend": "₹0",
                "roas": "0.00x",
                "performance": "pending",
                "message": "Connect your Meta account to start tracking campaigns.",
                "optimization_tip": [
                    "Connect Meta Ads to unlock AI-powered optimization",
                    "Access real-time campaign performance data",
                    "Get personalized recommendations for each campaign"
                ],
            }
        ]

    if not access_token or not account_id or not user_id:
        return [
            {
                "name": "Select Ad Account",
                "status": "setup",
                "spend": "₹0",
                "roas": "0.00x",
                "performance": "pending",
                "message": "Select an ad account to view campaigns.",
                "optimization_tip": [
                    "Select your primary ad account for personalized tips",
                    "Access detailed campaign performance metrics",
                    "Get AI-powered optimization recommendations"
                ],
            }
        ]

    try:
        # Get account currency first
        currency = await _get_account_currency(user_id, access_token, account_id)
        
        # Fetch ALL campaigns, their insights, and budgets using direct API
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        campaign_budgets = await meta_service.get_campaign_budgets(user_id, access_token, account_id)
        
        # If no campaigns at all, return early
        if not campaigns:
            return [
                {
                    "name": "No Campaigns Found",
                    "status": "setup",
                    "spend": "₹0",
                    "roas": "0.00x",
                    "performance": "pending",
                    "message": "No campaigns found in your ad account. Create campaigns in Meta Ads Manager.",
                    "optimization_tip": [
                        "Start with conversion campaigns for better ROI",
                        "Use detailed targeting based on customer data",
                        "Set up proper conversion tracking with Meta Pixel"
                    ],
                }
            ]
        
        # Create lookups for campaign data by campaign_id
        insights_lookup = {}
        for insight in campaign_insights:
            campaign_id = insight.get("campaign_id")
            if campaign_id:
                insights_lookup[campaign_id] = insight
        
        budgets_lookup = {}
        for budget in campaign_budgets:
            campaign_id = budget.get("id")
            if campaign_id:
                budgets_lookup[campaign_id] = budget
        
        # Build campaign list with real data - SHOW ACTIVE AND PAUSED CAMPAIGNS
        campaign_list = []
        for campaign in campaigns:
            campaign_id = campaign.get("id")
            campaign_name = campaign.get("name", "Unnamed Campaign")
            status = campaign.get("status", "UNKNOWN").upper()
            
            # Include ONLY ACTIVE campaigns
            if status != "ACTIVE":
                continue
            
            # Get insights for this campaign
            insight = insights_lookup.get(campaign_id, {})
            spend = float(insight.get("spend", 0))
            spend_str = _format_currency(spend, currency)
            
            # Get impressions and reach for this campaign
            impressions = int(insight.get("impressions", 0))
            reach = int(insight.get("reach", 0))
            
            # Get budget for this campaign
            budget_info = budgets_lookup.get(campaign_id, {})
            daily_budget = float(budget_info.get("daily_budget", 0) or 0)
            # Convert from cents to currency units (Meta API returns in cents)
            daily_budget = daily_budget / 100 if daily_budget > 0 else 0
            daily_budget_str = _format_currency(daily_budget, currency)
            
            # Get ROAS from Meta API (purchase_roas field)
            roas_value = insight.get("purchase_roas", [])
            if roas_value and len(roas_value) > 0:
                # Meta returns ROAS as array, get first value
                roas_num = float(roas_value[0].get("value", 0))
                roas_str = f"{roas_num:.2f}x"
            else:
                # Fallback: calculate ROAS manually if purchase_roas not available
                actions = insight.get("actions", []) or []
                action_values = insight.get("action_values", []) or []
                revenue = 0.0
                
                # Extract purchase values (revenue)
                for action_value in action_values:
                    action_type = action_value.get("action_type", "")
                    value = float(action_value.get("value", 0) or 0)
                    if "purchase" in action_type.lower() or "conversion" in action_type.lower():
                        revenue += value
                
                roas_str = _calculate_roas(spend, revenue) if spend > 0 else "0.00x"
                roas_num = float(roas_str.replace("x", "")) if roas_str != "0.00x" else 0
            
            if roas_num >= 3.0:
                performance = "excellent"
            elif roas_num >= 2.0:
                performance = "good"
            elif roas_num >= 1.0:
                performance = "average"
            else:
                performance = "poor"
            
            # Generate AI optimization recommendations for this campaign
            try:
                ai_recommendations = await _get_campaign_optimization_recommendation(
                    campaign_data=campaign,
                    insight_data=insight,
                    business_objective=objective
                )
            except Exception as e:
                # Campaign-specific fallback recommendations based on actual metrics
                campaign_name = campaign.get('name', 'Campaign')[:20]
                
                # Calculate conversions for fallback
                actions = insight.get("actions", []) or []
                conversions = 0
                for action in actions:
                    if "purchase" in action.get("action_type", "").lower():
                        conversions += int(action.get("value", 0))
                
                if roas_num >= 2.0:
                    ai_recommendations = [
                        f"Scale '{campaign_name}' budget by 30% - current {roas_str} ROAS is profitable",
                        f"Test lookalike audiences for this {roas_str} ROAS performer",
                        f"Expand targeting while maintaining {roas_str} performance level"
                    ]
                elif roas_num >= 1.0:
                    ai_recommendations = [
                        f"Optimize '{campaign_name}' creatives to push {roas_str} ROAS above 2.0x",
                        f"A/B test new audiences to improve {conversions} conversions",
                        f"Monitor {campaign_name} daily for performance improvements"
                    ]
                else:
                    ctr_val = (clicks / impressions * 100) if impressions > 0 else 0
                    ai_recommendations = [
                        f"'{campaign_name}' ROAS {roas_str} needs immediate attention",
                        f"Review targeting - current CTR {ctr_val:.1f}% may indicate poor fit",
                        f"Consider pausing {campaign_name} if metrics don't improve in 3 days"
                    ]
            
            campaign_list.append({
                "id": campaign_id,
                "name": campaign_name,
                "status": "active",  # Only active campaigns now
                "spend": spend_str,
                "roas": roas_str,
                "performance": performance,
                "impressions": _format_number(impressions) if impressions > 0 else "0",
                "reach": _format_number(reach) if reach > 0 else "0",
                "daily_budget": daily_budget_str if daily_budget > 0 else "₹0",
                "objective": campaign.get("objective", ""),
                "optimization_tip": ai_recommendations,
            })
        
        # If no active campaigns found, return a message
        if not campaign_list:
            return [
                {
                    "name": "No Active Campaigns Found",
                    "status": "setup",
                    "spend": "₹0",
                    "roas": "0.00x",
                    "performance": "pending",
                    "message": "No active campaigns found. Create or activate campaigns in Meta Ads Manager.",
                    "optimization_tip": [
                    "Create your first campaign with clear objectives",
                    "Target specific audience segments for better results",
                    "Set realistic daily budgets based on your goals"
                ],
                }
            ]
        
        return campaign_list
        
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Error in _build_campaigns: {e}")
        # Return error message campaign
        return [
            {
                "name": "Error Loading Campaigns",
                "status": "error",
                "spend": "₹0",
                "roas": "0.00x",
                "performance": "pending",
                "message": f"Unable to fetch campaigns: {str(e)}",
                "optimization_tip": [
                    "Check your Meta Ads connection and permissions",
                    "Refresh the page to reload campaign data",
                    "Contact support if the issue persists"
                ],
            }
        ]


def _build_notifications(business: models.BusinessProfile | None, meta_connected: bool, has_selected_account: bool) -> List[Dict]:
    notifications: List[Dict] = []

    if not business or not business.businessName:
        notifications.append(
            {"id": 1, "type": "warning", "message": "Add your business details to unlock tailored AI tips.", "time": "Just now"}
        )

    if not meta_connected:
        notifications.append(
            {
                "id": 2,
                "type": "warning",
                "message": "Meta Ads not connected. Connect to sync campaigns automatically.",
                "time": "5 min ago",
            }
        )
    elif not has_selected_account:
        notifications.append(
            {
                "id": 3,
                "type": "info",
                "message": "Select a primary ad account for personalized insights.",
                "time": "12 min ago",
            }
        )
    else:
        notifications.append(
            {
                "id": 4,
                "type": "success",
                "message": "Meta Ads synced successfully. Monitoring live performance.",
                "time": "1 hour ago",
            }
        )

    return notifications


async def _build_recommendations(
    meta_connected: bool, 
    objective: str | None,
    user_id: Optional[int] = None,
    access_token: Optional[str] = None,
    account_id: Optional[str] = None,
) -> List[Dict]:
    suggestions: List[Dict] = []

    if not meta_connected:
        suggestions.append(
            {
                "id": 1,
                "title": "Connect Meta Ads",
                "description": "Securely connect your Meta Ads account to unlock AI-powered campaign analytics and recommendations.",
                "status": "pending",
                "campaign": "Account Setup",
                "action": "connect_meta",
                "impact": "Enable Smart AI Insights",
            }
        )
        return suggestions

    if not access_token or not account_id or not user_id:
        suggestions.append(
            {
                "id": 1,
                "title": "Select Ad Account",
                "description": "Choose a primary ad account to get personalized AI recommendations with ROI projections.",
                "status": "pending",
                "campaign": "Account Setup",
                "action": "select_account",
                "impact": "Enable AI-Powered Recommendations",
            }
        )
        return suggestions

    try:
        # Fetch actual campaigns and their performance
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        account_insights = await meta_service.get_account_insights(user_id, access_token, account_id)
        
        # Use AI to generate intelligent recommendations
        from app.services.ai_recommendations import generate_ai_recommendations
        
        ai_recommendations = await generate_ai_recommendations(
            campaigns_data=campaigns,
            account_insights=account_insights,
            campaign_insights=campaign_insights,
            business_objective=objective,
            account_id=account_id
        )
        
        if ai_recommendations:
            return ai_recommendations
        
        # Fallback to rule-based recommendations if AI fails
        return await _build_rule_based_recommendations(campaigns, campaign_insights, objective)
        
    except Exception as e:
        logger.error(f"Error building recommendations: {e}")
        # Fallback recommendations if everything fails
        return [
            {
                "id": 1,
                "title": "Review Campaign Performance",
                "description": "Unable to fetch live data. Please review your campaigns manually in Meta Ads Manager.",
                "status": "pending",
                "campaign": "All Campaigns",
                "action": "manual_review",
                "impact": "Ensure optimal performance",
            }
        ]


async def _build_rule_based_recommendations(campaigns: List[Dict], campaign_insights: List[Dict], objective: str) -> List[Dict]:
    """Fallback rule-based recommendations when AI is not available."""
    suggestions: List[Dict] = []
    
    # Create insights lookup
    insights_lookup = {}
    for insight in campaign_insights:
        campaign_id = insight.get("campaign_id")
        if campaign_id:
            insights_lookup[campaign_id] = insight
    
    suggestion_id = 1
    
    # Analyze campaigns for recommendations
    for campaign in campaigns[:5]:  # Analyze top 5 campaigns
        campaign_id = campaign.get("id")
        campaign_name = campaign.get("name", "Unnamed Campaign")
        status = campaign.get("status", "UNKNOWN")
        
        insight = insights_lookup.get(campaign_id, {})
        spend = float(insight.get("spend", 0))
        
        # Calculate ROI
        actions = insight.get("actions", []) or []
        action_values = insight.get("action_values", []) or []
        revenue = 0.0
        
        for action_value in action_values:
            action_type = action_value.get("action_type", "")
            value = float(action_value.get("value", 0) or 0)
            if "purchase" in action_type.lower():
                revenue += value
        
        roi = ((revenue - spend) / spend * 100) if spend > 0 else 0
        
        # Generate recommendations based on performance
        if roi > 100 and spend > 50:  # High ROI campaign
            potential_revenue = spend * 0.5  # Estimate 50% increase
            suggestions.append(
                {
                    "id": suggestion_id,
                    "title": f'Scale High-Performing "{campaign_name[:30]}..." Campaign',
                    "description": f"Campaign showing {roi:.0f}% ROI. Increasing budget could scale profitable returns.",
                    "status": "pending",
                    "campaign": campaign_name,
                    "action": "increase_budget",
                    "impact": f"+₹{potential_revenue:.0f} potential revenue (Rule-based estimate)",
                }
            )
            suggestion_id += 1
        
        elif roi < -20 and spend > 20:  # Poor performing campaign
            daily_save = spend * 0.1  # Estimate daily savings
            suggestions.append(
                {
                    "id": suggestion_id,
                    "title": f'Optimize Underperforming "{campaign_name[:30]}..." Campaign',
                    "description": f"Campaign showing {roi:.0f}% ROI. Consider pausing or optimizing targeting to reduce losses.",
                    "status": "pending",
                    "campaign": campaign_name,
                    "action": "optimize_campaign",
                    "impact": f"Save ₹{daily_save:.0f}/day (Rule-based estimate)",
                }
            )
            suggestion_id += 1
        
        elif status.upper() == "PAUSED" and roi > 0:  # Paused profitable campaign
            suggestions.append(
                {
                    "id": suggestion_id,
                    "title": f'Reactivate Profitable "{campaign_name[:30]}..." Campaign',
                    "description": f"Previously profitable campaign (ROI: {roi:.0f}%) is currently paused.",
                    "status": "pending",
                    "campaign": campaign_name,
                    "action": "reactivate_campaign",
                    "impact": "Resume profitable traffic",
                }
            )
            suggestion_id += 1
    
    # Add objective-based recommendations
    if objective and "lead" in objective.lower():
        suggestions.append(
            {
                "id": suggestion_id,
                "title": "Optimize for Lead Generation",
                "description": "Your goal is lead generation. Consider using Meta's lead forms to reduce friction.",
                "status": "pending",
                "campaign": "All Campaigns",
                "action": "optimize_for_leads",
                "impact": "+25% lead conversion rate (Industry benchmark)",
            }
        )
        suggestion_id += 1
    
    # If no specific recommendations, add general ones
    if not suggestions:
        suggestions.append(
            {
                "id": 1,
                "title": "Campaign Performance Review",
                "description": "Your campaigns are running. Monitor performance and adjust targeting as needed.",
                "status": "pending",
                "campaign": "All Campaigns",
                "action": "monitor_performance",
                "impact": "Maintain optimal ROI",
            }
        )
    
    return suggestions[:3]  # Limit to 3 recommendations


@router.get("", response_model=schemas.DashboardResponse)
async def get_dashboard_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    business_result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = business_result.scalars().first()

    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    meta_connected = bool(integration)
    selected_ad_account = integration.selected_ad_account if integration else None
    ad_account_count = len(integration.ad_accounts or []) if integration else 0
    access_token = integration.access_token if integration else None

    # Fetch actual data from Meta Ads using MCP
    stats = await _build_stats(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
    )
    campaigns = await _build_campaigns(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
    )
    notifications = _build_notifications(business, meta_connected, bool(selected_ad_account))
    recommendations = await _build_recommendations(
        meta_connected, 
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
    )

    return {
        "stats": stats,
        "campaigns": campaigns,
        "notifications": notifications,
        "aiRecommendations": recommendations,
        "meta": {
            "connected": meta_connected,
            "selectedAdAccount": selected_ad_account,
            "adAccountCount": ad_account_count,
        },
        "business": {
            "businessName": business.businessName if business else None,
            "objective": business.objective if business else None,
            "websiteUrl": business.websiteUrl if business else None,
        },
        "generatedAt": datetime.utcnow(),
    }


@router.post("/recommendations/{recommendation_id}/status")
async def update_recommendation_status(
    recommendation_id: int,
    payload: schemas.RecommendationStatusUpdate,
    request: Request,
):
    _require_user_id(request)
    return {
        "id": recommendation_id,
        "status": payload.status,
        "message": "Status recorded. Persisted storage can be added later.",
    }


@router.get("/campaign/{campaign_id}")
async def get_campaign_details(
    campaign_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information for a specific campaign."""
    user_id = _require_user_id(request)

    # Get user's Meta integration
    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    if not integration or not integration.selected_ad_account:
        raise HTTPException(status_code=400, detail="Meta Ads not connected or no account selected")

    access_token = integration.access_token
    account_id = integration.selected_ad_account

    try:
        # Get account currency
        currency = await _get_account_currency(user_id, access_token, account_id)
        
        # Fetch campaign details
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        campaign_budgets = await meta_service.get_campaign_budgets(user_id, access_token, account_id)
        
        # Find the specific campaign
        campaign = next((c for c in campaigns if c.get("id") == campaign_id), None)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Find insights for this campaign
        insight = next((i for i in campaign_insights if i.get("campaign_id") == campaign_id), {})
        
        # Find budget for this campaign
        budget_info = next((b for b in campaign_budgets if b.get("id") == campaign_id), {})
        
        # Extract detailed metrics
        spend = float(insight.get("spend", 0))
        impressions = int(insight.get("impressions", 0))
        reach = int(insight.get("reach", 0))
        clicks = int(insight.get("clicks", 0))
        ctr = float(insight.get("ctr", 0))
        cpc = float(insight.get("cpc", 0))
        roas=float(insight.get("purchase_roas",0))
        
        # Budget information
        daily_budget = float(budget_info.get("daily_budget", 0) or 0) / 100  # Convert from cents
        lifetime_budget = float(budget_info.get("lifetime_budget", 0) or 0) / 100
        budget_remaining = float(budget_info.get("budget_remaining", 0) or 0) / 100
        
        # Calculate conversions and revenue
        actions = insight.get("actions", []) or []
        action_values = insight.get("action_values", []) or []
        conversions = 0
        revenue = 0.0
        
        for action in actions:
            action_type = action.get("action_type", "")
            value = int(action.get("value", 0) or 0)
            if any(keyword in action_type.lower() for keyword in ["purchase", "conversion", "lead", "complete_registration"]):
                conversions += value
        
        for action_value in action_values:
            action_type = action_value.get("action_type", "")
            value = float(action_value.get("value", 0) or 0)
            if "purchase" in action_type.lower() or "conversion" in action_type.lower():
                revenue += value
        
        roi = _calculate_roi(spend, revenue) if spend > 0 else "0%"
        
        return {
            "campaign": {
                "id": campaign_id,
                "name": campaign.get("name", ""),
                "status": campaign.get("status", "").lower(),
                "objective": campaign.get("objective", ""),
                "created_time": campaign.get("created_time", ""),
                "updated_time": campaign.get("updated_time", ""),
            },
            "performance": {
                "spend": _format_currency(spend, currency),
                "impressions": _format_number(impressions),
                "reach": _format_number(reach),
                "clicks": _format_number(clicks),
                "ctr": f"{ctr:.2f}%",
                "cpc": _format_currency(cpc, currency),
                "conversions": _format_number(conversions),
                "revenue": _format_currency(revenue, currency),
                "roi": roi,
                "roas":roas
            },
            "budget": {
                "daily_budget": _format_currency(daily_budget, currency) if daily_budget > 0 else "Not set",
                "lifetime_budget": _format_currency(lifetime_budget, currency) if lifetime_budget > 0 else "Not set",
                "budget_remaining": _format_currency(budget_remaining, currency) if budget_remaining > 0 else "₹0",
                "budget_type": "daily" if daily_budget > 0 else "lifetime" if lifetime_budget > 0 else "unknown",
            },
            "generatedAt": datetime.utcnow(),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch campaign details")
