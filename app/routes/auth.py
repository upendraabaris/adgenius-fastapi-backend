from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.db import AsyncSessionLocal
from app import models, schemas
from app.utils import security
from datetime import datetime, timedelta, timezone
import random
import jwt
from app.config import settings
from app.utils.email import send_otp_email, send_password_reset_email, send_verification_email

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return int(user_id)

@router.post("/signup", response_model=schemas.SignupResponse)
async def signup(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == user.email))
    existing = q.scalars().first()
    
    # Plan mapping
    plan_config = {
        "free": {"credits": 100, "days": 365},
        "starter": {"credits": 1000, "days": 30},
        "growth": {"credits": 10000, "days": 30}
    }
    
    selected_plan = user.plan if user.plan in plan_config else "free"
    config = plan_config[selected_plan]
    
    hashed = security.get_password_hash(user.password)
    
    otp = f"{random.randint(100000, 999999)}"
    otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    if existing:
        if existing.is_email_verified:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Reuse existing unverified user
        existing.name = user.name
        existing.passwordHash = hashed
        existing.credits_balance = config["credits"]
        existing.email_otp = otp
        existing.email_otp_expires_at = otp_expiry
        existing.updatedAt = datetime.utcnow()
        
        # Update or create subscription
        sub_q = await db.execute(select(models.Subscription).where(models.Subscription.user_id == existing.id))
        sub = sub_q.scalars().first()
        if sub:
            sub.plan = selected_plan
            sub.expires_at = datetime.utcnow() + timedelta(days=config["days"])
        else:
            new_sub = models.Subscription(
                user_id=existing.id,
                plan=selected_plan,
                status="active",
                amount=0,
                expires_at=datetime.utcnow() + timedelta(days=config["days"]),
            )
            db.add(new_sub)
            
        await db.commit()
        target_user = existing
    else:
        # Create new user
        new = models.User(
            email=user.email,
            passwordHash=hashed,
            name=user.name,
            credits_balance=config["credits"],
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow(),
            is_email_verified=False,
            email_otp=otp,
            email_otp_expires_at=otp_expiry
        )
        db.add(new)
        await db.commit()
        await db.refresh(new)
        
        new_sub = models.Subscription(
            user_id=new.id,
            plan=selected_plan,
            status="active",
            amount=0,
            expires_at=datetime.utcnow() + timedelta(days=config["days"]),
        )
        db.add(new_sub)
        await db.commit()
        target_user = new
        
    # Send OTP email
    send_otp_email(target_user.email, otp)
    
    return {
        "message": "OTP verification code sent to your email",
        "email": target_user.email
    }

@router.post("/verify-signup-otp")
async def verify_signup_otp(req: schemas.VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == req.email))
    user = q.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")
        
    if not user.email_otp or user.email_otp != req.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP code")
        
    # Expiration check
    expires_at = user.email_otp_expires_at
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if expires_at < now:
            raise HTTPException(status_code=400, detail="OTP code has expired")
            
    user.is_email_verified = True
    user.email_otp = None
    user.email_otp_expires_at = None
    await db.commit()
    
    token = security.create_access_token({"sub": str(user.id)})
    user_out = schemas.UserOut.from_orm(user)
    return {
        "user": user_out,
        "access_token": token,
        "token_type": "bearer"
    }

@router.post("/resend-otp")
async def resend_otp(req: schemas.ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == req.email))
    user = q.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")
        
    otp = f"{random.randint(100000, 999999)}"
    otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    user.email_otp = otp
    user.email_otp_expires_at = otp_expiry
    await db.commit()
    
    send_otp_email(user.email, otp)
    
    return {"message": "OTP resent successfully"}

@router.post("/forgot-password")
async def forgot_password(req: schemas.ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == req.email))
    user = q.scalars().first()
    
    # We return success message anyway to prevent email scanning
    if not user:
        return {"message": "If an account exists, a reset link has been sent to your email."}
        
    # Generate reset token (15 mins duration)
    reset_token = security.create_access_token({"sub": f"reset:{user.id}"}, expires_delta=15)
    
    send_password_reset_email(user.email, reset_token)
    
    return {"message": "If an account exists, a reset link has been sent to your email."}

@router.post("/reset-password")
async def reset_password(req: schemas.ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(req.token, settings.SECRET_KEY, algorithms=["HS256"])
        sub: str = payload.get("sub")
        if not sub or not sub.startswith("reset:"):
            raise HTTPException(status_code=400, detail="Invalid token")
        user_id = int(sub.split(":")[1])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Password reset link has expired")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid password reset link")
        
    q = await db.execute(select(models.User).where(models.User.id == user_id))
    user = q.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    hashed = security.get_password_hash(req.password)
    user.passwordHash = hashed
    await db.commit()
    
    return {"message": "Password has been reset successfully."}

@router.post("/login", response_model=schemas.Token)
async def login(form: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == form.email))
    user = q.scalars().first()
    if not user or not security.verify_password(form.password, user.passwordHash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.is_email_verified:
        raise HTTPException(status_code=400, detail="Please verify your email first.")
        
    token = security.create_access_token({"sub": str(user.id)})
    return {"access_token": token}


@router.post("/send-verification-email")
async def send_verification_email_route(req: schemas.ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == req.email))
    user = q.scalars().first()
    
    # Return success even if user not found or already verified to prevent email enumeration
    if not user:
        return {"message": "Verification link has been sent to your email."}
        
    if user.is_email_verified:
        return {"message": "Email is already verified."}
        
    # Generate verification token (24 hours = 1440 minutes duration)
    verify_token = security.create_access_token({"sub": f"verify:{user.id}"}, expires_delta=1440)
    
    send_verification_email(user.email, verify_token)
    
    return {"message": "Verification link has been sent to your email."}


@router.post("/verify-email-token")
async def verify_email_token(req: schemas.VerifyEmailTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(req.token, settings.SECRET_KEY, algorithms=["HS256"])
        sub: str = payload.get("sub")
        if not sub or not sub.startswith("verify:"):
            raise HTTPException(status_code=400, detail="Invalid token")
        user_id = int(sub.split(":")[1])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Verification link has expired")
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid verification link")
        
    q = await db.execute(select(models.User).where(models.User.id == user_id))
    user = q.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not user.is_email_verified:
        user.is_email_verified = True
        await db.commit()
        
    token = security.create_access_token({"sub": str(user.id)})
    user_out = schemas.UserOut.from_orm(user)
    return {
        "user": user_out,
        "access_token": token,
        "token_type": "bearer"
    }



@router.get("/profile")
async def get_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the authenticated user's profile information along with business details.
    """
    user_id = _require_user_id(request)

    user_result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    business_result = await db.execute(
        select(models.BusinessProfile)
        .where(models.BusinessProfile.userId == user_id)
        .order_by(desc(models.BusinessProfile.updatedAt))
    )
    business = business_result.scalars().first()

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "credits_balance": user.credits_balance,
        "businessName": business.businessName if business else None,
        "objective": business.objective if business else None,
        "websiteUrl": business.websiteUrl if business else None,
    }

