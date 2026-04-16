from datetime import datetime
from typing import Dict, List, Optional
import logging
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models, schemas
from app.services import meta_service, ai_recommendations
from app.utils.auth import _require_user_id, _require_active_subscription, _get_user_subscription
from app.utils.credits import deduct_credits, estimate_tokens

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


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
    """Get the currency of the ad account with improved fallback."""
    try:
        # Check cache or user preferences if needed, but let's stick to Meta API for now
        if not account_id:
            return "INR" # Default to INR for GrowCommerce users if ID is missing
            
        # Ensure account_id has 'act_' prefix
        clean_id = account_id
        if not clean_id.startswith('act_'):
            clean_id = f'act_{clean_id}'
        
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{clean_id}",
                params={
                    "access_token": access_token,
                    "fields": "currency,account_id",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("currency", "INR")
            else:
                logger.warning(f"Meta API currency fetch failed: {resp.text}")
                return "INR" # Smarter fallback to INR for this repo's context
    except Exception as e:
        logger.error(f"Error fetching account currency: {e}")
        return "INR"  # Default fallback to INR


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


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default

def extract_conversions(insight_dict: Dict) -> int:
    """Helper to extract conversion count from Meta insight actions."""
    actions = insight_dict.get("actions", []) or []
    total = 0
    for a in actions:
        if any(k in a.get("action_type", "").lower() for k in ["purchase", "conversion", "lead", "complete_registration"]):
            total += safe_int(a.get("value", 0))
    return total

def _calculate_roas(spend: float, revenue: float) -> str:
    """Calculate ROAS (Return on Ad Spend) ratio."""
    if spend == 0:
        return "0.00x"
    roas = revenue / spend
    return f"{roas:.2f}x"

async def _get_campaign_optimization_recommendation(
    user_id: int,
    access_token: str,
    account_id: str,
    campaign_data: Dict,
    insight_data: Dict,
    business_objective: Optional[str] = None,
    website_url: Optional[str] = None
) -> tuple[List[str], int]:
    """
    Generate professional AI-powered audit bullets for a specific campaign.
    Returns (List[str], int) -> (tips, tokens)
    """
    campaign_id = campaign_data.get("id")
    campaign_name = campaign_data.get("name", "Unnamed")
    
    try:
        # Fetch real demographic and geographic data
        breakdowns = await meta_service.get_campaign_audience_breakdowns(user_id, access_token, campaign_id)
        
        # Extract metrics for the AI audit
        spend = float(insight_data.get("spend", 0))
        
        # ROAS
        roas_data = insight_data.get("purchase_roas", [])
        roas = float(roas_data[0].get("value", 0)) if roas_data and len(roas_data) > 0 else 0.0
        
        # Conversions (Purchase/Leads)
        actions = insight_data.get("actions", []) or []
        conversions = 0
        for action in actions:
            action_type = action.get("action_type", "")
            if any(keyword in action_type.lower() for keyword in ["purchase", "conversion", "lead", "complete_registration"]):
                conversions += int(action.get("value", 0) or 0)
        
        cpr = spend / conversions if conversions > 0 else 0
        ctr = float(insight_data.get("ctr", 0))
        
        # Call the new specialized AI helper for a professional "Audit-Grade" output
        from app.services.ai_recommendations import generate_campaign_mini_audit
        recommendations, tokens = await generate_campaign_mini_audit(
            campaign_name=campaign_name,
            spend=spend,
            roas=roas,
            conversions=conversions,
            cpr=cpr,
            ctr=ctr,
            breakdowns=breakdowns,
            business_objective=business_objective
        )
        
        return recommendations[:10], tokens

    except Exception as e:
        logger.error(f"Error generating professional campaign audit: {e}")
        fallback = ["Monitor performance across demographic segments for scaling opportunities."]
        return fallback, estimate_tokens(str(fallback))


@router.get("/campaigns/{campaign_id}/review")
async def review_campaign_optimization(
    campaign_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch both AI tips and Ad Set list for the Review & Apply modal.
    """
    user_id = _require_user_id(request)
    
    # Get user's meta connection from Integration table
    meta_conn = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == 'meta'
        )
    )
    meta_conn = meta_conn.scalars().first()
    
    if not meta_conn:
        raise HTTPException(status_code=400, detail="Meta account not connected")
        
    access_token = meta_conn.access_token
    selected_accounts = meta_conn.selected_ad_accounts or []
    account_id = selected_accounts[0] if selected_accounts else None
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # 1. Start all data fetching in parallel for speed
            adsets_task = meta_service.get_campaign_adsets(user_id, access_token, campaign_id)
            
            as_ins_task = client.get(
                f"https://graph.facebook.com/v20.0/{campaign_id}/insights",
                params={
                    "access_token": access_token, 
                    "level": "adset",
                    "fields": "adset_id,spend,reach,purchase_roas",
                    "date_preset": "last_30d"
                }
            )
            
            c_meta_task = client.get(
                f"https://graph.facebook.com/v20.0/{campaign_id}",
                params={"access_token": access_token, "fields": "name,objective"}
            )
            
            c_ins_task = client.get(
                f"https://graph.facebook.com/v20.0/{campaign_id}/insights",
                params={
                    "access_token": access_token, 
                    "fields": "spend,purchase_roas,actions,ctr",
                    "date_preset": "last_30d"
                }
            )
            
            biz_profile_task = db.execute(
                select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
            )

            # Wait for all main data tasks
            adsets, as_ins_resp, c_meta_resp, c_ins_resp, biz_profile_res = await asyncio.gather(
                adsets_task, as_ins_task, c_meta_task, c_ins_task, biz_profile_task
            )

            # 2. Process Ad Set Insights
            as_ins_map = {}
            if as_ins_resp.status_code == 200:
                as_insights = as_ins_resp.json().get("data", [])
                as_ins_map = {i.get("adset_id"): i for i in as_insights if i.get("adset_id")}

            # Identify Currency from Integration Metadata
            curr = "INR"
            if meta_conn.ad_accounts:
                acc_list = meta_conn.ad_accounts if isinstance(meta_conn.ad_accounts, list) else []
                # Try to find currency of the current account_id
                matched_acc = next((acc for acc in acc_list if acc.get("account_id") == account_id), None)
                if not matched_acc and acc_list:
                    matched_acc = acc_list[0]
                if matched_acc:
                    curr = matched_acc.get("currency") or matched_acc.get("account_currency", "INR")

            for adset in adsets:
                ins = as_ins_map.get(adset.get("id"), {})
                
                # Format Spend
                try:
                    spend_val = float(ins.get("spend", 0))
                    adset["spend"] = _format_currency(spend_val, curr)
                except:
                    adset["spend"] = _format_currency(0, curr)
                
                # Format Budgets
                if adset.get("daily_budget"):
                    try:
                        adset["daily_budget"] = _format_currency(float(adset["daily_budget"])/100, curr)
                    except: pass
                if adset.get("lifetime_budget"):
                    try:
                        adset["lifetime_budget"] = _format_currency(float(adset["lifetime_budget"])/100, curr)
                    except: pass
                    
                adset["reach"] = int(ins.get("reach", 0))
                
                # Safe ROAS extraction
                roas_val = "0.00x"
                roas_data = ins.get("purchase_roas", [])
                if roas_data and isinstance(roas_data, list) and len(roas_data) > 0:
                    try:
                        roas_val = f"{float(roas_data[0].get('value', 0)):.2f}x"
                    except:
                        pass
                adset["roas"] = roas_val

            # 3. Process Campaign Stats for AI
            campaign_data = c_meta_resp.json()
            insights_list = c_ins_resp.json().get("data", [])
            insight_data = insights_list[0] if insights_list else {}
            
            biz_profile = biz_profile_res.scalars().first()
            biz_obj = biz_profile.objective if biz_profile else None

            # 4. Generate AI tips (Correctly unpacking the tuple: [tips], tokens)
            tips_result = await _get_campaign_optimization_recommendation(
                user_id=user_id,
                access_token=access_token,
                account_id=account_id,
                campaign_data=campaign_data,
                insight_data=insight_data,
                business_objective=biz_obj
            )
            
            # Tips is actually (tips_list, total_tokens)
            tips = tips_result[0] if isinstance(tips_result, tuple) else tips_result
            
            logger.info(f"REVIEW ENDPOINT: campaign={campaign_id}, adsets_count={len(adsets)}, tips_count={len(tips)}")

            return {
                "campaign_name": campaign_data.get("name", "Unknown Campaign"),
                "tips": tips,
                "adsets": adsets
            }
        
    except Exception as e:
        logger.error(f"Error in review_campaign_optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}/history")
async def get_campaign_optimization_history(
    campaign_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch the list of optimizations performed on a campaign from the database.
    """
    user_id = _require_user_id(request)
    result = await db.execute(
        select(models.OptimizationHistory)
        .where(models.OptimizationHistory.user_id == user_id)
        .where(models.OptimizationHistory.campaign_id == campaign_id)
        .order_by(models.OptimizationHistory.created_at.desc())
    )
    history = result.scalars().all()
    return history


@router.post("/history/{history_id}/restore")
async def restore_optimization_snapshot(
    history_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Rollback to a specific 'before_config' from the history.
    """
    user_id = _require_user_id(request)
    
    # 1. Fetch history record
    result = await db.execute(
        select(models.OptimizationHistory).where(
            models.OptimizationHistory.id == history_id,
            models.OptimizationHistory.user_id == user_id
        )
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="History record not found")
        
    # 2. Get Meta connection
    integration = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == 'meta'
        )
    )
    integration = integration.scalars().first()
    if not integration:
        raise HTTPException(status_code=400, detail="Meta account not connected")
        
    # 3. Restore to Meta
    try:
        update_result = await meta_service.update_adset_configuration(
            user_id, integration.access_token, record.adset_id, record.before_config
        )
        
        if update_result.get("success"):
            record.status = "restored"
            await db.commit()
            return {"success": True, "message": "Manual restore successful"}
        else:
            raise HTTPException(status_code=500, detail=f"Meta restore failed: {update_result.get('error')}")
            
    except Exception as e:
        logger.error(f"Error restoring from history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/{campaign_id}/apply")
async def apply_campaign_optimization(
    campaign_id: str,
    payload: schemas.ApplyOptimizationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Apply AI recommendations with transactional rollback & DB audit logging.
    """
    user_id = _require_user_id(request)
    
    # Check plan - Block Free users
    sub = await _get_user_subscription(db, user_id)
    if not sub or sub.plan == "free":
        raise HTTPException(
            status_code=403, 
            detail="Optimization application is a premium feature. Please upgrade to Starter or Growth plan."
        )
    
    # 1. Get credentials
    integration = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == 'meta'
        )
    )
    integration = integration.scalars().first()
    if not integration:
        raise HTTPException(status_code=400, detail="Meta account not connected")
        
    access_token = integration.access_token
    
    selected_tips = payload.selected_tips
    selected_adset_ids = payload.selected_adset_ids
    
    try:
        # STEP A: Snapshotting - Parallel backup of current configs
        backup_tasks = [
            meta_service.get_adset_configuration(user_id, access_token, aid) 
            for aid in selected_adset_ids
        ]
        backup_results = await asyncio.gather(*backup_tasks)
        adset_backups = {
            aid: config for aid, config in zip(selected_adset_ids, backup_results) if config
        }
        
        applied_results = []
        successfully_updated_ids = []
        total_optimization_tokens = 0
        
        # STEP B: Apply optimizations per ad set
        for adset_id in selected_adset_ids:
            current_config = adset_backups.get(adset_id)
            if not current_config:
                continue
            
            # 1. AI Translation
            update_payload, tokens = await ai_recommendations.translate_strategy_to_params(
                selected_tips, current_config
            )
            total_optimization_tokens += tokens
            
            # 2. Add DB Log (Audit Trail)
            history_record = models.OptimizationHistory(
                user_id=user_id,
                campaign_id=campaign_id,
                adset_id=adset_id,
                before_config=current_config,
                after_config=update_payload,
                strategy_tips=selected_tips,
                status="pending"
            )
            db.add(history_record)
            await db.flush() # Get history_record.id
            
            # 3. Push to Meta
            meta_update = await meta_service.update_adset_configuration(
                user_id, access_token, adset_id, update_payload
            )
            
            if meta_update.get("success"):
                history_record.status = "applied"
                applied_results.append({"adset_id": adset_id, "success": True})
                successfully_updated_ids.append(adset_id)
            else:
                # CRITICAL: Trigger Rollback for previous adsets in this transaction
                history_record.status = "failed"
                history_record.error_message = meta_update.get("error")
                
                logger.warning(f"Optimization failed for adset {adset_id}. Initiating rollback for batch.")
                
                rollback_tasks = [
                    meta_service.update_adset_configuration(
                        user_id, access_token, aid, adset_backups[aid]
                    ) for aid in successfully_updated_ids
                ]
                await asyncio.gather(*rollback_tasks)
                
                # Mark history as rolled_back
                for prev_id in successfully_updated_ids:
                    # Update DB status (This is slightly inefficient, ideally update in bulk)
                    await db.execute(
                        update(models.OptimizationHistory)
                        .where(models.OptimizationHistory.user_id == user_id)
                        .where(models.OptimizationHistory.adset_id == prev_id)
                        .where(models.OptimizationHistory.status == "applied")
                        .values(status="rolled_back")
                    )
                
                await db.commit()
                return {
                    "success": False, 
                    "error": f"Failed at {current_config.get('name') or adset_id}. All changes rolled back.",
                    "details": meta_update.get("error")
                }
        
        # STEP C: Deduct credits for all AI translations performed
        if total_optimization_tokens > 0:
            await deduct_credits(db, user_id, total_optimization_tokens)
            
        await db.commit()
        return {"success": True, "results": applied_results}

    except Exception as e:
        logger.error(f"Bulk optimization error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


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
        roas_value = "0.00x"
        conversions_value = "0"
        spend_change = "—"
        campaigns_change = "—"
        conversions_change = "—"
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
            
            spend_change = "+0%"
            campaigns_change = "0"
            conversions_change = "+0%"
            
        except Exception as e:
            logger.error(f"Error in _build_stats fallback: {e}")
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
    website_url: Optional[str] = None,
) -> tuple[List[Dict], int]:
    """Build campaigns list from actual Meta Ads data if available. Returns (campaigns, total_tokens)"""
    
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
        ], 0

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
        ], 0

    try:
        # Get account currency first
        currency = await _get_account_currency(user_id, access_token, account_id)
        
        # Fetch ALL campaigns, their insights, and budgets using direct API
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        campaign_budgets = await meta_service.get_campaign_budgets(user_id, access_token, account_id)
        account_insights = await meta_service.get_account_insights(user_id, access_token, account_id)
        
        # Calculate Avg CTR for Benchmarking
        acc_clicks = 0
        acc_imps = 1
        if isinstance(account_insights, dict):
            acc_clicks = int(account_insights.get("clicks", 0) or 0)
            acc_imps = int(account_insights.get("impressions", 1) or 1)
        elif isinstance(account_insights, list) and len(account_insights) > 0:
            first = account_insights[0]
            acc_clicks = int(first.get("clicks", 0) or 0)
            acc_imps = int(first.get("impressions", 1) or 1)
            
        avg_ctr_base = (acc_clicks / acc_imps * 100) if acc_imps > 0 else 1.5
        
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
            ], 0
        
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
        
        # Pre-process active campaigns and prepare AI recommendation tasks
        active_campaign_data = []
        ai_tasks = []
        
        for campaign in campaigns:
            campaign_id = campaign.get("id")
            campaign_name = campaign.get("name", "Unnamed Campaign")
            status = campaign.get("status", "UNKNOWN").upper()
            
            if status != "ACTIVE":
                continue
                
            insight = insights_lookup.get(campaign_id, {})
            budget_info = budgets_lookup.get(campaign_id, {})
            
            active_campaign_data.append({
                "campaign": campaign,
                "insight": insight,
                "budget_info": budget_info
            })
            
            # Add to AI task list
            ai_tasks.append(
                _get_campaign_optimization_recommendation(
                    user_id=user_id,
                    access_token=access_token,
                    account_id=account_id,
                    campaign_data=campaign,
                    insight_data=insight,
                    business_objective=objective,
                    website_url=website_url
                )
            )
            
        # Execute all AI audit tasks in parallel
        ai_responses = await asyncio.gather(*ai_tasks)
        
        # Merge AI audit results back into active_campaign_data
        total_ai_tokens = 0
        ai_idx = 0
        for i, campaign in enumerate(active_campaign_data):
            if campaign.get("campaign", {}).get("status", "").upper() == "ACTIVE":
                tips, tokens = ai_responses[ai_idx]
                campaign["optimization_tip"] = tips
                total_ai_tokens += tokens
                ai_idx += 1
        
        # Build the final campaign list
        campaign_list = []
        for idx, data in enumerate(active_campaign_data):
            campaign = data["campaign"]
            insight = data["insight"]
            budget_info = data["budget_info"]
            campaign_id = campaign.get("id")
            campaign_name = campaign.get("name", "Unnamed Campaign")
            
            spend = float(insight.get("spend", 0))
            spend_str = _format_currency(spend, currency)
            impressions = int(insight.get("impressions", 0))
            reach = int(insight.get("reach", 0))
            
            daily_budget = float(budget_info.get("daily_budget", 0) or 0) / 100
            daily_budget_str = _format_currency(daily_budget, currency)
            
            # ROAS and Conversion logic (match KPI Stats logic for consistency)
            meta_actions = insight.get("actions", []) or []
            roas_value = insight.get("purchase_roas", [])
            roas_num = float(roas_value[0].get("value", 0)) if roas_value and len(roas_value) > 0 else 0.0
            roas_str = f"{roas_num:.2f}x"
            
            conversions = 0
            for action in meta_actions:
                action_type = action.get("action_type", "").lower()
                value = action.get("value", 0)
                print(f"{action_type} => {value}")

                if any(k in action_type for k in ["lead", "complete_registration", "purchase","conversions"]):
                    conversions += int(value or 0)

            cpr_num = spend / conversions if conversions > 0 else 0
            cpr_str = _format_currency(cpr_num, currency) if conversions > 0 else "—"
            
            if roas_num >= 3.0:
                performance = "excellent"
            elif roas_num >= 2.0:
                performance = "good"
            elif roas_num >= 1.0:
                performance = "average"
            else:
                performance = "poor"

            # Get AI recommendations from previously processed results in data
            ai_tips = data.get("optimization_tip", ["Monitoring campaign performance..."])
            
            # Other Meta Metrics
            meta_clicks = insight.get("clicks", "0")
            meta_ctr = insight.get("ctr", "0")
            meta_cpc = insight.get("cpc", "0")
            meta_frequency = insight.get("frequency", "0")
            
            # --- INLINE PERFORMANCE MATRIX (6-Point Diagnostic) ---
            p_matrix = []
            import datetime
            curr_h = datetime.datetime.utcnow().hour + 5.5 # IST
            
            # 1. Creative Fatigue
            freq_val = float(insight.get("frequency", 0))
            ctr_val = float(insight.get("ctr", 0))
            if freq_val < 2.0:
                p_matrix.append({"point": "Creative Fatigue", "status": "healthy", "suggestion": "Frequency is below 2, indicating fresh audience exposure."})
            elif freq_val > 3.5:
                p_matrix.append({"point": "Creative Fatigue", "status": "alert", "suggestion": "High Frequency (3.5+). Audience fatigue detected. Refresh creatives."})
            else:
                p_matrix.append({"point": "Creative Fatigue", "status": "healthy", "suggestion": "Creative health is stable within optimal range."})
                
            # 2. Audience Overlap
            p_matrix.append({"point": "Audience Overlap", "status": "healthy", "suggestion": "No significant overlap detected for this campaign."})
            
            # 3. Budget Pacing
            if daily_budget > 0 and spend > (daily_budget * 0.8) and curr_h < 17:
                p_matrix.append({"point": "Budget Pacing", "status": "alert", "suggestion": "Campaign is consuming budget aggressively. Monitor pacing."})
            else:
                p_matrix.append({"point": "Budget Pacing", "status": "healthy", "suggestion": "Budget pacing is optimal across the day."})
                
            # 4. Funnel Leakage
            try:
                m_clicks_int = int(meta_clicks or 0)
                if m_clicks_int > 50 and conversions == 0:
                    p_matrix.append({"point": "Funnel Leakage", "status": "warning", "suggestion": "High clicks but zero conversions. Check landing page speed and checkout flow."})
                else:
                    p_matrix.append({"point": "Funnel Leakage", "status": "healthy", "suggestion": "Funnel flow is efficient and converting."})
            except:
                p_matrix.append({"point": "Funnel Leakage", "status": "healthy", "suggestion": "Funnel flow diagnostics stable."})
                
            # 5. Winning Scaling
            if roas_num >= 3.0:
                p_matrix.append({"point": "Winning Scaling", "status": "strong", "suggestion": f"Strong ROAS ({roas_num:.2f}x). Increase budget by 20% to scale results."})
            elif roas_num >= 2.0:
                p_matrix.append({"point": "Winning Scaling", "status": "strong", "suggestion": "ROAS is above 2. Increase budget by 20% to scale."})
            else:
                p_matrix.append({"point": "Winning Scaling", "status": "neutral", "suggestion": "Monitor performance for future scaling potential."})
                
            # 6. Industry Benchmark
            ind_ctr = 1.5
            if ctr_val >= 1.8:
                p_matrix.append({"point": "Benchmark", "status": "healthy", "suggestion": f"Outperforming Industry Avg ({ind_ctr}%). CTR: {ctr_val:.2f}%."})
            elif ctr_val >= ind_ctr:
                p_matrix.append({"point": "Benchmark", "status": "average", "suggestion": "CTR is within average range. Optimize creatives to improve."})
            else:
                p_matrix.append({"point": "Benchmark", "status": "warning", "suggestion": f"Below Industry Avg ({ind_ctr}%). Improve creative hooks."})

            campaign_list.append({
                "id": campaign_id,
                "name": campaign_name,
                "status": "active",
                "spend": spend_str,
                "roas": roas_str,
                "conversions": _format_number(conversions),
                "cpr": cpr_str,
                "performance": performance,
                "impressions": _format_number(impressions) if impressions > 0 else "0",
                "reach": _format_number(reach) if reach > 0 else "0",
                "daily_budget": daily_budget_str if daily_budget > 0 else "₹0",
                "objective": campaign.get("objective", ""),
                "optimization_tip": ai_tips,
                "performance_matrix": p_matrix,
                "clicks": meta_clicks,
                "ctr": f"{float(meta_ctr):.2f}%" if meta_ctr else "0.00%",
                "cpc": _format_currency(float(meta_cpc), currency) if meta_cpc else "₹0.00",
                "frequency": f"{float(meta_frequency):.2f}" if meta_frequency else "0.00",
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
            ], 0
        
        # [DEBUG] Print final campaign list to console
        # print(f"\n{'='*20} FINAL CAMPAIGN LIST {'='*20}")
        # import json
        # print(json.dumps(campaign_list, indent=2))
        # print(f"{'='*20} END OF CAMPAIGN LIST {'='*20}\n")
        
        return campaign_list, total_ai_tokens
        
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
        ], 0


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
    website_url: Optional[str] = None,
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
        
        # Use Strategic Matrix Logic as primary insight tool
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
    """6-Point Strategic Performance Matrix Diagnostic."""
    matrix = []

    # 1. Calculate Account Average CTR for Benchmarking
    total_spend = sum(safe_float(i.get("spend")) for i in campaign_insights)
    total_clicks = sum(safe_int(i.get("clicks")) for i in campaign_insights)
    total_imps = sum(safe_int(i.get("impressions", 1)) for i in campaign_insights)
    total_conversions = 0
    
    for insight in campaign_insights:
        actions = insight.get("actions", []) or []
        for a in actions:
            if any(k in a.get("action_type", "").lower() for k in ["purchase", "conversion", "lead"]):
                total_conversions += safe_int(a.get("value", 0))
    
    avg_ctr = (total_clicks / total_imps * 100) if total_imps > 0 else 0
    avg_roas = sum(safe_float(i.get("purchase_roas", 0)) for i in campaign_insights) / len(campaign_insights) if campaign_insights else 0
    
    logger.info(f"Generating Performance Matrix for {len(campaign_insights)} campaigns. Avg CTR: {avg_ctr}%")
    
    # --- RULE 1: Creative Fatigue ---
    fatigued_campaigns = [i for i in campaign_insights if safe_float(i.get("frequency")) > 3.5 and safe_float(i.get("ctr")) < (avg_ctr * 0.8)]
    matrix.append({
        "id": "fatigue",
        "title": "Creative Fatigue Level",
        "status": "alert" if fatigued_campaigns else "healthy",
        "impact": "High Impact",
        "description": f"AI detected {len(fatigued_campaigns)} campaigns with frequency > 3.5 and dropping CTR. Meta ad audience fatigue is increasing." if fatigued_campaigns else "Creative health is stable. Frequency and CTR are within optimal range.",
        "suggestion": "Naye creatives upload karein taaki audience fatigue kam ho aur CTR wapas increase ho sake." if fatigued_campaigns else "Continue with current creative strategy."
    })
    
    # --- RULE 2: Audience Overlap ---
    active_adsets = len(campaigns) # Proxy for now
    matrix.append({
        "id": "overlap",
        "title": "Audience Overlap Check",
        "status": "warning" if active_adsets > 3 else "healthy",
        "impact": "Medium Impact",
        "description": "Multi-adset competition detected. Interest segments may be overlapping in the auction." if active_adsets > 3 else "Audience segments are well-segmented with minimal overlap.",
        "suggestion": "Interests segments ko merge karein taaki CPC kam ho sake aur aapas mein competition na ho." if active_adsets > 3 else "Targeting is efficient."
    })
    
    # --- RULE 3: Budget Pacing ---
    import datetime
    current_hour = datetime.datetime.utcnow().hour + 5.5 # IST approximation
    is_early_exhaustion = any(safe_float(i.get("spend")) > 0.8 * (safe_float(i.get("daily_budget", 1))) for i in campaign_insights) and current_hour < 16
    matrix.append({
        "id": "pacing",
        "title": "Budget Exhaustion & Pacing",
        "status": "alert" if is_early_exhaustion else "healthy",
        "impact": "High Impact",
        "description": "Daily budget is exhausting too fast before peak conversion hours (evening)." if is_early_exhaustion else "Budget is pacing evenly across the day.",
        "suggestion": "Campaign budget badhaein ya peak hours (sham) ke liye schedule karein taaki sales miss na hon." if is_early_exhaustion else "Pacing is optimal."
    })
    
    # --- RULE 4: Funnel Leakage Detection ---
    is_leakage = any(safe_int(i.get("clicks")) > 100 and (extract_conversions(i) / safe_int(i.get("clicks", 1))) < 0.01 for i in campaign_insights)
    matrix.append({
        "id": "leakage",
        "title": "Funnel Leakage Detection",
        "status": "alert" if is_leakage else "healthy",
        "impact": "High Impact",
        "description": "High link clicks but extremely low conversion rate detected (Click-to-Purchase gap)." if is_leakage else "Funnel conversion rate is within healthy parameters.",
        "suggestion": "Landing Page speed ya Checkout page check karein. Add to carts toh hain par purchases nahi ho rahi." if is_leakage else "Funnel is leak-free."
    })
    
    # --- RULE 5: Winning Audience Scaling ---
    winning_camps = [i for i in campaign_insights if safe_float(i.get("purchase_roas")) > 3.0]
    matrix.append({
        "id": "scaling",
        "title": "Winning Audience Scaling",
        "status": "healthy" if winning_camps else "neutral",
        "impact": "High Impact",
        "description": f"Detected {len(winning_camps)} segments with 3x+ ROAS. High efficiency scaling potential." if winning_camps else "No high-performing segments identified for aggressive scaling yet.",
        "suggestion": f"In specific 'Winning' segments par budget 20% badhane se overall performance increase hogi." if winning_camps else "Monitor current performance for winners."
    })
    
    # --- RULE 6: Industry Benchmarks ---
    industry_ctr = 1.5
    matrix.append({
        "id": "benchmarks",
        "title": "Industry Benchmarks",
        "status": "healthy" if avg_ctr >= industry_ctr else "warning",
        "impact": "Benchmark",
        "description": f"Account CTR is {avg_ctr:.2f}% vs Industry Average of {industry_ctr}%.",
        "suggestion": "Aap outperform kar rahe hain!" if avg_ctr >= industry_ctr else "Creative hooks ko improve karein taaki account CTR 1.5% benchmark tak pahuch sake."
    })

    return matrix
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


@router.post("/generate-report")
async def generate_report_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate a professional AI audit report for the ad account."""
    user_id = _require_user_id(request)
    await _require_active_subscription(db, user_id)
    
    # 1. Get Integration/Access Token
    integration = (await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )).scalars().first()
    
    selected_accounts = integration.selected_ad_accounts if integration else []
    if not integration or not integration.access_token or not selected_accounts:
        raise HTTPException(status_code=400, detail="Meta Ads not connected or no account selected")
    
    access_token = integration.access_token
    account_id = selected_accounts[0] # Using priority account for now
    
    # 2. Get Business Profile (for Objective)
    business = (await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )).scalars().first()
    
    try:
        # 3. Fetch Data in parallel/sequence
        # Account-level insights
        account_insights = await meta_service.get_account_insights(user_id, access_token, account_id)
        
        # Get all campaigns to check their status
        campaigns = await meta_service.get_campaigns(user_id, access_token, account_id)
        active_campaign_ids = [c.get("id") for c in campaigns if c.get("status", "").upper() == "ACTIVE"]
        
        # Campaign-level insights
        all_campaign_insights = await meta_service.get_campaign_insights(user_id, access_token, account_id)
        
        # Filter: ONLY campaigns that are currently ACTIVE
        active_campaign_insights = [
            insight for insight in all_campaign_insights 
            if insight.get("campaign_id") in active_campaign_ids
        ]
        
        # Audience Breakdowns (we need these for the report)
        # We'll get breakdowns for the top-performing ACTIVE campaign to keep it focused
        audience_data = []
        if active_campaign_insights:
            top_campaign_id = active_campaign_insights[0].get("campaign_id")
            if top_campaign_id:
                audience_data = await meta_service.get_campaign_audience_breakdowns(
                    user_id, access_token, top_campaign_id
                )
        
        # 4. Generate the Report using AI (passing only ACTIVE insights)
        report_markdown, tokens = await ai_recommendations.generate_account_audit_report(
            account_insights=account_insights,
            campaign_insights=active_campaign_insights,
            audience_breakdowns=audience_data,
            business_objective=(business.objective if business else None)
        )
        
        # 5. Deduct Credits
        await deduct_credits(db, user_id, tokens)
        
        return {"report": report_markdown, "generatedAt": datetime.utcnow(), "tokens_used": tokens}
        
    except Exception as e:
        logger.error(f"Error generating report endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard stats only - for progressive loading."""
    user_id = _require_user_id(request)
    await _require_active_subscription(db, user_id)

    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    
    business_result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = business_result.scalars().first()

    meta_connected = bool(integration)
    access_token = integration.access_token if integration else None

    stats = await _build_stats(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
    )

    return {"stats": stats, "generatedAt": datetime.utcnow()}


@router.get("/campaigns")
async def get_dashboard_campaigns(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard campaigns only - for progressive loading."""
    user_id = _require_user_id(request)
    await _require_active_subscription(db, user_id)

    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    
    business_result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = business_result.scalars().first()

    meta_connected = bool(integration)
    access_token = integration.access_token if integration else None

    campaigns, tokens = await _build_campaigns(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
        business.websiteUrl if business else None,
    )
    
    # Deduct credits for any AI tips generated in build_campaigns
    if tokens > 0:
        await deduct_credits(db, user_id, tokens)

    return {"campaigns": campaigns, "generatedAt": datetime.utcnow()}


@router.get("/notifications")
async def get_dashboard_notifications(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard notifications only - very fast, no API calls."""
    user_id = _require_user_id(request)
    await _require_active_subscription(db, user_id)

    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    
    business_result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = business_result.scalars().first()
    
    meta_connected = bool(integration)
    has_selected_account = bool(integration and selected_accounts)

    notifications = _build_notifications(business, meta_connected, has_selected_account)

    return {"notifications": notifications, "generatedAt": datetime.utcnow()}


@router.get("/recommendations")
async def get_dashboard_recommendations(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard recommendations only - can be slow."""
    user_id = _require_user_id(request)
    await _require_active_subscription(db, user_id)

    integration_result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = integration_result.scalars().first()

    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    
    business_result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = business_result.scalars().first()
    
    meta_connected = bool(integration)
    access_token = integration.access_token if integration else None

    recommendations = await _build_recommendations(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
        business.websiteUrl if business else None,
    )

    return {"aiRecommendations": recommendations, "generatedAt": datetime.utcnow()}


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
    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    ad_account_count = len(integration.ad_accounts or []) if integration else 0
    access_token = integration.access_token if integration else None

    # Helper function to convert sync to async
    async def _get_notifications():
        return _build_notifications(business, meta_connected, bool(selected_ad_account))
    
    # Call separate endpoint functions in parallel
    stats_task = _build_stats(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
    )
    campaigns_task = _build_campaigns(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
        business.websiteUrl if business else None,
    )
    notifications_task = _get_notifications()
    recommendations_task = _build_recommendations(
        meta_connected,
        business.objective if business else None,
        user_id,
        access_token,
        selected_ad_account,
        business.websiteUrl if business else None,
    )

    stats, (campaigns, camp_tokens), notifications, recommendations = await asyncio.gather(
        stats_task,
        campaigns_task,
        notifications_task,
        recommendations_task
    )

    # Deduct credits for overview load
    if camp_tokens > 0:
        await deduct_credits(db, user_id, camp_tokens)

    return {
        "stats": stats,
        "campaigns": campaigns,
        "notifications": notifications,
        "aiRecommendations": recommendations,
        "meta": {
            "connected": meta_connected,
            "selectedAdAccount": selected_ad_account,
            "selectedAdAccounts": selected_accounts,
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

    selected_accounts = integration.selected_ad_accounts if integration else []
    selected_ad_account = selected_accounts[0] if selected_accounts else None
    if not integration or not selected_ad_account:
        raise HTTPException(status_code=400, detail="Meta Ads not connected or no account selected")

    access_token = integration.access_token
    account_id = selected_ad_account

    try:
        # Get account currency
        currency = await _get_account_currency(user_id, access_token, account_id)
        
        # Fetch campaign details in parallel
        campaigns, campaign_insights, campaign_budgets = await asyncio.gather(
            meta_service.get_campaigns(user_id, access_token, account_id),
            meta_service.get_campaign_insights(user_id, access_token, account_id),
            meta_service.get_campaign_budgets(user_id, access_token, account_id)
        )
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