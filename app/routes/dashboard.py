from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models, schemas
from app.services import meta_service


router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


def _format_currency(amount: float) -> str:
    """Format amount as currency string."""
    if amount >= 1000:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _format_number(num: int | float) -> str:
    """Format number with commas."""
    return f"{int(num):,}"


def _calculate_roi(spend: float, revenue: float) -> str:
    """Calculate ROI percentage."""
    if spend == 0:
        return "0%"
    roi = ((revenue - spend) / spend) * 100
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.0f}%"


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
        spend_value = "$0"
        campaigns_value = "0"
        roi_value = "0%"
        conversions_value = "0"
        spend_change = "0%"
        campaigns_change = "0"
        roi_change = "0%"
        conversions_change = "0%"
    else:
        try:
            # Fetch actual insights using MCP
            insights = await meta_service.get_account_insights(user_id, access_token, account_id)
            campaigns_data = await meta_service.get_campaigns(user_id, access_token, account_id)
            
            # Calculate spend
            spend = float(insights.get("spend", 0))
            spend_value = _format_currency(spend)
            
            # Count active campaigns
            active_campaigns = [c for c in campaigns_data if c.get("status") == "ACTIVE"]
            campaigns_value = str(len(active_campaigns))
            
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
            
            # Calculate ROI (using purchase value as revenue)
            roi_value = _calculate_roi(spend, revenue) if spend > 0 else "0%"
            
            # For changes, we'd need historical data - using placeholder for now
            # In production, you'd compare with previous period
            spend_change = "+0%"
            campaigns_change = "0"
            roi_change = "+0%"
            conversions_change = "+0%"
            
        except Exception as e:
            # Fallback to defaults if API call fails
            spend_value = "$0"
            campaigns_value = "0"
            roi_value = "0%"
            conversions_value = "0"
            spend_change = "0%"
            campaigns_change = "0"
            roi_change = "0%"
            conversions_change = "0%"

    return [
        {"id": "spend", "title": "Total Spend", "value": spend_value, "change": spend_change, "trend": "up" if spend_change.startswith("+") else "down"},
        {"id": "campaigns", "title": "Active Campaigns", "value": campaigns_value, "change": campaigns_change, "trend": "up" if campaigns_change.startswith("+") else "down"},
        {"id": "roi", "title": "Avg. ROI", "value": roi_value, "change": roi_change, "trend": "up" if roi_change.startswith("+") else "down"},
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
                "spend": "$0",
                "roi": "+0%",
                "performance": "pending",
                "message": "Connect your Meta account to start tracking campaigns.",
            }
        ]

    if not access_token or not account_id or not user_id:
        return [
            {
                "name": "Select Ad Account",
                "status": "setup",
                "spend": "$0",
                "roi": "+0%",
                "performance": "pending",
                "message": "Select an ad account to view campaigns.",
            }
        ]

    try:
        # Fetch actual campaigns and their insights using MCP
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        
        # Create a lookup for campaign insights by campaign_id
        insights_lookup = {}
        for insight in campaign_insights:
            campaign_id = insight.get("campaign_id")
            if campaign_id:
                insights_lookup[campaign_id] = insight
        
        # Build campaign list with real data
        campaign_list = []
        for campaign in campaigns[:10]:  # Limit to 10 campaigns
            campaign_id = campaign.get("id")
            campaign_name = campaign.get("name", "Unnamed Campaign")
            status = campaign.get("status", "UNKNOWN").lower()
            
            # Get insights for this campaign
            insight = insights_lookup.get(campaign_id, {})
            spend = float(insight.get("spend", 0))
            spend_str = _format_currency(spend)
            
            # Calculate ROI from insights
            actions = insight.get("actions", []) or []
            action_values = insight.get("action_values", []) or []
            revenue = 0.0
            
            # Extract purchase values (revenue)
            for action_value in action_values:
                action_type = action_value.get("action_type", "")
                value = float(action_value.get("value", 0) or 0)
                if "purchase" in action_type.lower():
                    revenue += value
            
            roi_str = _calculate_roi(spend, revenue) if spend > 0 else "0%"
            
            # Determine performance based on ROI
            roi_num = float(roi_str.replace("+", "").replace("%", "")) if roi_str.replace("+", "").replace("%", "").replace("-", "").isdigit() else 0
            if roi_num > 50:
                performance = "excellent"
            elif roi_num > 0:
                performance = "good"
            elif roi_num > -10:
                performance = "average"
            else:
                performance = "poor"
            
            campaign_list.append({
                "name": campaign_name,
                "status": status,
                "spend": spend_str,
                "roi": roi_str,
                "performance": performance,
            })
        
        # If no campaigns found, return a message
        if not campaign_list:
            return [
                {
                    "name": "No Campaigns Found",
                    "status": "setup",
                    "spend": "$0",
                    "roi": "+0%",
                    "performance": "pending",
                    "message": "Create your first campaign in Meta Ads Manager.",
                }
            ]
        
        return campaign_list
        
    except Exception as e:
        # Fallback to default message if API call fails
        return [
            {
                "name": "Error Loading Campaigns",
                "status": "error",
                "spend": "$0",
                "roi": "+0%",
                "performance": "pending",
                "message": f"Unable to fetch campaigns. Please try again later.",
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


def _build_recommendations(meta_connected: bool, objective: str | None) -> List[Dict]:
    suggestions: List[Dict] = []

    if not meta_connected:
        suggestions.append(
            {
                "id": 1,
                "title": "Connect Meta Ads",
                "description": "Securely connect your Meta Ads account to unlock live campaign analytics.",
                "status": "pending",
                "campaign": "Account Setup",
                "action": "connect_meta",
                "impact": "Enable Smart Insights",
            }
        )
        return suggestions

    increase_title = 'Increase Budget for "Summer Sale"'
    pause_title = 'Pause "Winter Promo" Campaign'

    suggestions.append(
        {
            "id": 1,
            "title": increase_title,
            "description": "High-performing campaign with 145% ROI. Reinvest budget to scale returns.",
            "status": "pending",
            "campaign": "Summer Sale",
            "action": "increase_budget",
            "impact": "+$450 revenue",
        }
    )

    suggestions.append(
        {
            "id": 2,
            "title": pause_title,
            "description": "Detected negative ROI. Pausing now can save spend and reallocate to winners.",
            "status": "pending",
            "campaign": "Winter Promo",
            "action": "pause_campaign",
            "impact": "Save $150/day",
        }
    )

    if objective and "lead" in objective.lower():
        suggestions.append(
            {
                "id": 3,
                "title": "Switch to Lead Forms",
                "description": "Goal is lead generation. Use on-platform lead forms to reduce drop-off.",
                "status": "pending",
                "campaign": "Lead Magnet",
                "action": "switch_objective",
                "impact": "+35% qualified leads",
            }
        )

    return suggestions


@router.get("/", response_model=schemas.DashboardResponse)
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
    recommendations = _build_recommendations(meta_connected, business.objective if business else None)

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

