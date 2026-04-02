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
            "temperature": 0.0,
            "max_tokens": 4000
        }
    )

async def generate_ai_recommendations(
    campaigns_data: List[Dict],
    account_insights: Dict,
    campaign_insights: List[Dict],
    business_objective: Optional[str] = None,
    account_id: Optional[str] = None,
    website_url: Optional[str] = None
) -> List[Dict]:
    """
    Generate AI-powered recommendations using Claude Haiku.
    
    Returns recommendations with ROI impact estimates and actionable insights.
    """
    try:
        llm = get_ai_llm()
        
        # Fetch website content if URL is provided
        website_content = ""
        print(f"\n{'='*100}")
        print(f"🔍 STARTING WEBSITE EXTRACTION")
        print(f"Website URL: {website_url}")
        print(f"{'='*100}\n")
        
        if website_url:
            try:
                import requests
                from bs4 import BeautifulSoup
                
                print(f"⏳ Fetching website: {website_url}")
                response = requests.get(website_url, timeout=5)
                print(f"✅ Response Status Code: {response.status_code}")
                
                if response.status_code == 200:
                    print(f"✅ Website fetched successfully!")
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract key information
                    title = soup.find('title')
                    meta_desc = soup.find('meta', attrs={'name': 'description'})
                    headings = soup.find_all(['h1', 'h2'])[:5]
                    
                    # Extract text from paragraphs (limit to first 1000 chars)
                    paragraphs = soup.find_all('p')[:5]
                    text_content = ' '.join([p.get_text(strip=True) for p in paragraphs])[:1000]
                    
                    # Print website information to console
                    print(f"\n{'='*100}")
                    print(f"🌐 WEBSITE INFORMATION EXTRACTED:")
                    print(f"{'='*100}")
                    print(f"URL: {website_url}")
                    print(f"Title: {title.text.strip() if title else 'N/A'}")
                    print(f"Meta Description: {meta_desc.get('content', 'N/A') if meta_desc else 'N/A'}")
                    print(f"Key Headings: {[h.get_text(strip=True) for h in headings]}")
                    print(f"Content Summary: {text_content}")
                    print(f"{'='*100}\n")
                    
                    website_content = f"""
WEBSITE INFORMATION:
- URL: {website_url}
- Title: {title.text.strip() if title else 'N/A'}
- Meta Description: {meta_desc.get('content', 'N/A') if meta_desc else 'N/A'}
- Key Headings: {[h.get_text(strip=True) for h in headings]}
- Content Summary: {text_content}
"""
                else:
                    print(f"❌ Failed to fetch website. Status Code: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"⏱️ TIMEOUT: Website request timed out: {website_url}")
                website_content = f"\nWEBSITE: {website_url} (Request timeout)"
            except Exception as e:
                print(f"❌ ERROR fetching website: {e}")
                website_content = f"\nWEBSITE: {website_url} (Could not fetch: {str(e)[:100]})"
        else:
            print(f"⚠️  No website URL provided")
        
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
You are an expert Meta Ads consultant. Analyze the following campaign data and business website to provide exactly 3 actionable recommendations.

{website_content}

ACCOUNT DATA:
{json.dumps(data_summary, indent=2)}

REQUIREMENTS:
1. Provide specific, data-driven recommendations
2. Include ROI impact estimates (be realistic based on current performance)
3. Focus on the most impactful optimizations aligned with website content
4. Identify any mismatches between ad messaging and website value propositions
5. Recommend budget allocation based on products/services shown on website
6. Consider the business objective: {business_objective or 'general performance'}

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

Focus on Indian market-specific optimizations:
- Budget allocation considering Indian cost structures (CPC/CPM in ₹)
- Audience targeting for Indian demographics, languages, and regions
- Timing optimizations for Indian time zones and peak hours
- Content localization for Indian audience preferences
- Festival/seasonal campaign planning for India
- Platform preferences in India (WhatsApp, Instagram, Facebook usage patterns)
- Mobile-first optimization for Indian users (high mobile usage)
- Regional language considerations where applicable

Provide realistic ROI projections based on current performance data and Indian market benchmarks.
All monetary mentions should be in ₹ (Indian Rupees).
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

async def generate_account_audit_report(
    account_insights: Dict,
    campaign_insights: List[Dict],
    audience_breakdowns: List[Dict],
    business_objective: Optional[str] = None
) -> str:
    """
    Generate a professional Markdown-formatted Meta Ads Account Audit.
    """
    try:
        llm = get_ai_llm()
        
        # Helper to extract ROAS
        def extract_roas(insight: Dict) -> float:
            roas_list = insight.get("purchase_roas", []) or []
            if roas_list and len(roas_list) > 0:
                return float(roas_list[0].get("value", 0))
            # Fallback calculation if spend and revenue are available
            return 0.0

        # Helper to extract conversions
        def extract_conversions(insight: Dict) -> int:
            actions = insight.get("actions", []) or []
            conversions = 0
            for action in actions:
                action_type = action.get("action_type", "")
                if any(keyword in action_type.lower() for keyword in ["purchase", "conversion", "lead", "complete_registration"]):
                    conversions += int(action.get("value", 0))
            return conversions

        # Prepare a rich data summary for the AI
        acct_conversions = extract_conversions(account_insights)
        acct_spend = float(account_insights.get("spend", 0))
        
        data_summary = {
            "account_overview": {
                "spend": acct_spend,
                "impressions": int(account_insights.get("impressions", 0)),
                "clicks": int(account_insights.get("clicks", 0)),
                "ctr": float(account_insights.get("ctr", 0)),
                "cpc": float(account_insights.get("cpc", 0)),
                "roas": extract_roas(account_insights),
                "conversions": acct_conversions,
                "cpr": (acct_spend / acct_conversions) if acct_conversions > 0 else 0
            },
            "campaign_performance": [],
            "audience_winners": audience_breakdowns,
            "objective": business_objective or "Maximize ROI"
        }
        
        for insight in campaign_insights[:5]:  # Focus on top 5
            camp_spend = float(insight.get("spend", 0))
            camp_conversions = extract_conversions(insight)
            data_summary["campaign_performance"].append({
                "name": insight.get("campaign_name", "Unknown"),
                "spend": camp_spend,
                "roas": extract_roas(insight),
                "conversions": camp_conversions,
                "cpr": (camp_spend / camp_conversions) if camp_conversions > 0 else 0
            })
            
        prompt = f"""
        You are a Senior Meta Ads Consultant at **GrowCommerce**, a top-tier digital growth agency.
        Generate a professional, deep-dive "GrowCommerce Executive Audit Report" for the following Meta Ads account data.
        
        DATA:
        {json.dumps(data_summary, indent=2)}
        
        REPORT REQUIREMENTS:
        1. Tone: Professional, authoritative, and data-driven.
        2. Format: Use clean Markdown (headings, tables, bold text, bullet points). **IMPORTANT: Ensure Markdown tables have a proper header row and use newlines between every row. Do not put multiple table rows on the same line.**
        3. Language: English (with currency references in ₹ if applicable).
        4. Focus on the last 30 days of performance.
        
        SECTIONS TO INCLUDE:
        - ✨ **Executive Summary**: A 2-3 sentence high-level overview of account health.
        - 🚀 **Scalability Analysis**: Identify which campaigns are ready to be scaled and why (based on ROAS and Efficiency).
        - 🎯 **Targeting Efficiency**: Analyze the Audience Winners. Who is converting cheapest? Who is wasting budget?
        - 📉 **Budget Leakage**: Where is money being spent without return?
        - 🔮 **30-Day Forecast**: If recommendations are applied, what is the conservative growth projection?
        - ✅ **High-Impact Checklist**: Exactly 5 bullet points of next steps.
        
        Output only the Markdown report content following this EXACT structure:
        
        # GrowCommerce Executive Audit Report
        
        ## ✨ Executive Summary
        [2-3 sentences of high-level overview]
        
        ## 🚀 Scalability Analysis
        [Identify top candidates for scaling in a Markdown table with Name, ROAS, and CPR columns]
        
        ## 🎯 Targeting Efficiency
        ### Winners
        [Bullet points of best performing segments]
        ### Wastage
        [Bullet points of segments with high spend but low return]
        
        ## 📉 Budget Leakage
        [Specific findings on where budget is being lost]
        
        ## 🔮 30-Day Performance Forecast
        [A table or list showing conservative vs optimistic growth if recommendations are followed]
        
        ## ✅ GrowCommerce Checklist
        [Exactly 5 actionable bullet points for next steps]
        
        **CONFIDENTIAL | Generated by GrowCommerce Strategy Team**
        """
        
        response = await llm.ainvoke(prompt)
        return response.content
        
    except Exception as e:        return "# AI Audit Report\n\nUnable to generate report at this time. Please check your data connection and try again later."

async def generate_campaign_mini_audit(
    campaign_name: str,
    spend: float,
    roas: float,
    conversions: int,
    cpr: float,
    ctr: float,
    breakdowns: Dict,
    business_objective: Optional[str] = None
) -> List[str]:
    """
    Generate professional, agency-grade audit bullets for a single campaign using LLM.
    Acts as a Senior Meta Ads Consultant at GrowCommerce.
    """
    try:
        llm = get_ai_llm()
        
        data_summary = {
            "campaign_name": campaign_name,
            "metrics": {
                "spend": spend,
                "roas": roas,
                "conversions": conversions,
                "cpr": cpr,
                "ctr": ctr
            },
            "audience_data": breakdowns,
            "objective": business_objective or "Maximize ROI"
        }
        
        # [DEBUG] Print raw data to console for verification
        print(f"\n{'='*20} RAW DATA START: {campaign_name} {'='*20}")
        print(json.dumps(data_summary, indent=2))
        print(f"{'='*20} RAW DATA END {'='*20}\n")
        
        prompt = f"""
        You are a Senior Meta Ads Consultant at **GrowCommerce**, a world-class performance marketing agency.
        Your goal is to provide a high-authority, technical "Executive Audit" for the following campaign data.
        
        CAMPAIGN DATA:
        {json.dumps(data_summary, indent=2)}
        
        INSTRUCTIONS:
        1. Tone: Deeply analytical, authoritative, and data-backed (Senior Meta Ads Strategist).
        2. Format: Return exactly 6 highly professional bullet points as a JSON list of strings.
        3. Content Structure: 
           - Bullet 1 (✨ Demographic Winner): Identify the best age/gender segments.
           - Bullet 2 (⚠️ Demographic Wastage): Identify underperforming age/gender segments.
           - Bullet 3 (🌍 Geographic Audit): Identify top-performing Regions/States (e.g., "Chandigarh", "Delhi").
           - Bullet 4 (📍 Regional Wastage): Identify states or regions with high CPR and low efficiency.
           - Bullet 5 (🎯 Targeting Roadmap): Explicit "Expand/Exclude" instructions for demographics.
           - Bullet 6 (🚀 Scaling Action): Specific budget or bidding next step for the whole campaign.
        4. Style: Use exact names from the breakdown data (e.g., "Delhi", "25-34 female").
        5. Currency: All monetary values in ₹ (Indian Rupees).
        
        RESPONSE FORMAT (JSON only):
        ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5", "bullet 6"]
        """
        
        response = await llm.ainvoke(prompt)
        content = response.content
        
        # Clean and parse JSON
        import re
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
        
    except Exception as e:
        logger.error(f"Error generating high-authority campaign audit: {e}")
        # Rule-based professional fallback if AI fails
        return [
            f"✨ **Winner Insight**: The campaign is maintaining a foundational {roas:.2f}x ROAS with {conversions} verified conversions.",
            "⚠️ **Wastage Warning**: Monitor high-frequency segments where CTR is trailing the account average to prevent budget fatigue.",
            f"🚀 **Scaling Strategy**: Prioritize budget consolidation into your top-performing 20% audience segments to boost capital efficiency."
        ]


async def translate_strategy_to_params(selected_tips: List[str], current_configuration: Dict) -> Dict:
    """
    Translate textual AI strategy tips into structured Meta API parameters.
    Uses LLM to map natural language to specific targeting/budget fields.
    """
    try:
        llm = get_ai_llm()
        
        prompt = f"""
        You are a Technical Ad Ops specialist at **GrowCommerce**. 
        Translate the following textual growth strategies into a valid JSON object for the Meta Ads API.
        
        STRATEGIES TO APPLY:
        {json.dumps(selected_tips, indent=2)}
        
        CURRENT AD SET CONFIGURATION (for reference):
        {json.dumps(current_configuration, indent=2)}
        
        CRITICAL RULES FOR META API COMPLIANCE:
        1. Output ONLY a valid JSON object. No markdown, no explanations.
        2. Supported keys: `daily_budget` (Integer in paise), `targeting` (Object).
        3. For `targeting`:
           - `age_min`: Integer (18-65).
           - `age_max`: Integer (18-65).
           - `genders`: Array of integers ([1] for Male, [2] for Female, or [1,2]).
           - `geo_locations`: 
             - `countries`: MUST be an array of ISO country codes (e.g., ["IN"]).
             - `regions`: DO NOT use string IDs like "IN_CH". ONLY use an array of objects with numeric keys if known (e.g. [{"key": "4004"}]). 
             - IMPORTANT: If the strategy mentions a specific region (like "Delhi") but you don't know its numeric Meta Key, DO NOT add it to `regions`. Keep the existing `geo_locations` from the current configuration instead.
        4. Budget: Meta uses integers in paise. If current `daily_budget` is "50000" (₹500), and you increase it by 20%, the new value must be 60000.
        
        RESPONSE FORMAT:
        {{
            "targeting": {{
                "age_min": 25,
                "age_max": 45,
                "genders": [1, 2],
                "geo_locations": {{ "countries": ["IN"] }}
            }},
            "daily_budget": 60000
        }}
        """
        
        response = await llm.ainvoke(prompt)
        content = response.content
        
        # Clean and parse JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
        
    except Exception as e:
        logger.error(f"Error translating strategy to params: {e}")
        return {}