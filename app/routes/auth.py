from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from app.db import AsyncSessionLocal
from app import models, schemas
from app.utils import security
from datetime import datetime

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
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = security.get_password_hash(user.password)
    new = models.User(
        email=user.email,
        passwordHash=hashed,
        name=user.name,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow()
    )
    db.add(new)
    await db.commit()
    await db.refresh(new)
    
    # Generate a token for the new user
    token = security.create_access_token({"sub": str(new.id)})
    
    # Convert the SQLAlchemy user object to a Pydantic model
    user_out = schemas.UserOut.from_orm(new)
    
    # Return the user details and token
    return {
        "user": user_out,
        "access_token": token,
        "token_type": "bearer"
    }

@router.post("/login", response_model=schemas.Token)
async def login(form: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == form.email))
    user = q.scalars().first()
    if not user or not security.verify_password(form.password, user.passwordHash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = security.create_access_token({"sub": str(user.id)})
    return {"access_token": token}


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
        "businessName": business.businessName if business else None,
        "objective": business.objective if business else None,
        "websiteUrl": business.websiteUrl if business else None,
    }

