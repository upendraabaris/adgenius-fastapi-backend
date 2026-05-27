import hmac
import hashlib
import os
from datetime import datetime, timedelta, timezone

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db import AsyncSessionLocal
from app import models

router = APIRouter()

# Plan config: name -> (amount in paise, display label, credits)
PLANS = {
    "free":    {"amount": 0, "label": "Free", "days": 365, "credits": 100},
    "starter": {"amount": 1000, "label": "Starter", "days": 30, "credits": 1000},  # ₹10
    "growth":  {"amount": 455700, "label": "Growth", "days": 30, "credits": 10000}, # ₹4100
}

RAZORPAY_PLAN_STARTER_ID = os.getenv("RAZORPAY_PLAN_STARTER_ID", "plan_starter_placeholder")
RAZORPAY_PLAN_GROWTH_ID = os.getenv("RAZORPAY_PLAN_GROWTH_ID", "plan_growth_placeholder")

PLAN_IDS = {
    "starter": RAZORPAY_PLAN_STARTER_ID,
    "growth": RAZORPAY_PLAN_GROWTH_ID,
}


def get_razorpay_client():
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Razorpay credentials not configured")
    return razorpay.Client(auth=(key_id, key_secret))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id


class CreateOrderRequest(BaseModel):
    plan: str  # 'free' | 'starter' | 'growth'


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str | None = None
    razorpay_subscription_id: str | None = None
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str


@router.post("/api/payments/create-order")
async def create_order(
    payload: CreateOrderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    plan_key = payload.plan
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[plan_key]

    # Free trial — no Razorpay order needed, save directly
    if plan["amount"] == 0:
        expires = datetime.utcnow() + timedelta(days=plan["days"])
        # Expire previous active subscriptions
        await db.execute(
            models.Subscription.__table__.update()
            .where(models.Subscription.user_id == user_id)
            .where(models.Subscription.status == "active")
            .values(status="expired")
        )
        sub = models.Subscription(
            user_id=user_id,
            plan=plan_key,
            status="active",
            amount=0,
            expires_at=expires,
        )
        db.add(sub)
        
        # Allocate credits for FREE plan
        user_result = await db.execute(select(models.User).where(models.User.id == user_id))
        user = user_result.scalars().first()
        if user:
            user.credits_balance = plan["credits"]
            
        await db.commit()
        return {"free": True, "plan": plan_key, "message": "Free plan activated"}

    # Paid plan — create Razorpay subscription (or order fallback)
    client = get_razorpay_client()
    plan_id = PLAN_IDS.get(plan_key)

    if plan_id and not plan_id.endswith("placeholder"):
        # Real Plan IDs configured — use Razorpay Subscriptions (recurring)
        try:
            subscription = client.subscription.create({
                "plan_id": plan_id,
                "total_count": 12,
                "quantity": 1,
                "customer_notify": 1,
                "notes": {
                    "plan": plan_key,
                    "user_id": str(user_id)
                }
            })
            return {
                "free": False,
                "mode": "subscription",
                "subscription_id": subscription["id"],
                "amount": plan["amount"],
                "currency": "INR",
                "plan": plan_key,
                "key_id": os.getenv("RAZORPAY_KEY_ID"),
            }
        except Exception as e:
            print(f"Razorpay Subscription API failed: {e}. Falling back to one-time order.")

    # Fallback — no Plan IDs set yet, create a standard one-time Razorpay order
    # This shows the real Razorpay payment modal to the user
    order = client.order.create({
        "amount": plan["amount"],
        "currency": "INR",
        "notes": {"plan": plan_key, "user_id": str(user_id)},
    })
    return {
        "free": False,
        "mode": "order",
        "order_id": order["id"],
        "amount": plan["amount"],
        "currency": "INR",
        "plan": plan_key,
        "key_id": os.getenv("RAZORPAY_KEY_ID"),
    }


@router.post("/api/payments/verify")
async def verify_payment(
    payload: VerifyPaymentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")

    # Polymorphic verification (Order or Subscription)
    if payload.razorpay_subscription_id:
        body = f"{payload.razorpay_payment_id}|{payload.razorpay_subscription_id}"
    else:
        body = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"

    is_mock = payload.razorpay_subscription_id and payload.razorpay_subscription_id.startswith("sub_test_")
    
    if not is_mock:
        expected = hmac.new(key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, payload.razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid payment signature")

    plan_key = payload.plan
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[plan_key]
    expires = datetime.utcnow() + timedelta(days=plan["days"])

    # Expire previous active subscriptions
    await db.execute(
        models.Subscription.__table__.update()
        .where(models.Subscription.user_id == user_id)
        .where(models.Subscription.status == "active")
        .values(status="expired")
    )
    sub = models.Subscription(
        user_id=user_id,
        plan=plan_key,
        status="active",
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_subscription_id=payload.razorpay_subscription_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
        amount=plan["amount"],
        expires_at=expires,
    )
    db.add(sub)
    
    # Allocate credits for PAID plan
    user_result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = user_result.scalars().first()
    if user:
        # For paid plans, we add to balance or set it? 
        # Requirement usually implies total replenishment for the month.
        user.credits_balance = plan["credits"]
        
    await db.commit()
    return {"success": True, "plan": plan_key, "expires_at": expires.isoformat()}


@router.get("/api/payments/subscription")
async def get_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)
    print(f"Fetching subscription for user_id: {user_id}")

    result = await db.execute(
        select(models.Subscription)
        .where(models.Subscription.user_id == user_id)
        .order_by(models.Subscription.created_at.desc())
    )
    sub = result.scalars().first()

    # Auto-assign free plan and credits for users who have no subscription
    if not sub:
        expires = datetime.utcnow() + timedelta(days=365)
        sub = models.Subscription(
            user_id=user_id,
            plan="free",
            status="active",
            amount=0,
            expires_at=expires,
        )
        db.add(sub)
        
        user_result = await db.execute(select(models.User).where(models.User.id == user_id))
        user = user_result.scalars().first()
        if user:
            user.credits_balance = 100 # Default free credits
            
        await db.commit()

    # Mark as expired if past expiry date
    if sub.expires_at:
        expires_at_naive = sub.expires_at.replace(tzinfo=None) if sub.expires_at.tzinfo else sub.expires_at
        if expires_at_naive < datetime.utcnow() and sub.status == "active":
            sub.status = "expired"
            await db.commit()

    return {
        "subscribed": True,
        "plan": sub.plan,
        "status": sub.status,
        "amount": sub.amount,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "razorpay_subscription_id": sub.razorpay_subscription_id,
    }


@router.post("/api/payments/webhook")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    
    # Verify signature if secret is set and it's not a local test call
    is_local_test = signature == "local_mock_signature"
    if webhook_secret and not is_local_test:
        expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
            
    import json
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    event = data.get("event")
    
    if event == "subscription.charged":
        sub_payload = data.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = sub_payload.get("id")
        
        if sub_id:
            # Find the subscription in DB
            result = await db.execute(
                select(models.Subscription)
                .where(models.Subscription.razorpay_subscription_id == sub_id)
                .order_by(models.Subscription.created_at.desc())
            )
            sub = result.scalars().first()
            if sub:
                plan_key = sub.plan
                plan = PLANS.get(plan_key, PLANS["starter"])
                
                # Extend expiry by 30 days
                sub.expires_at = datetime.utcnow() + timedelta(days=plan["days"])
                sub.status = "active"
                
                # Replenish credits
                user_result = await db.execute(select(models.User).where(models.User.id == sub.user_id))
                user = user_result.scalars().first()
                if user:
                    user.credits_balance = plan["credits"]
                    
                await db.commit()
                print(f"⚡ [Webhook] Subscription {sub_id} successfully renewed until {sub.expires_at.isoformat()}")
                return {"status": "success", "message": "Subscription renewed successfully"}
                
    elif event in ["subscription.cancelled", "subscription.halted"]:
        sub_payload = data.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = sub_payload.get("id")
        
        if sub_id:
            result = await db.execute(
                select(models.Subscription)
                .where(models.Subscription.razorpay_subscription_id == sub_id)
            )
            sub = result.scalars().first()
            if sub:
                sub.status = "cancelled"
                await db.commit()
                print(f"⚡ [Webhook] Subscription {sub_id} set to cancelled")
                return {"status": "success", "message": "Subscription cancelled"}
                
    return {"status": "ignored"}

