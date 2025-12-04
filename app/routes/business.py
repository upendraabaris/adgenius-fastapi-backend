from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db import AsyncSessionLocal
from app import models, schemas
from datetime import datetime

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", response_model=schemas.BusinessCreate)
async def create_business(
    request: Request,  # Access the request object to get user_id
    b: schemas.BusinessCreate,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.state.user_id  # Extract user_id from the middleware

    result = await db.execute(
        select(models.BusinessProfile).where(models.BusinessProfile.userId == user_id)
    )
    business = result.scalars().first()

    if business:
        business.businessName = b.businessName
        business.objective = b.objective
        business.websiteUrl = b.websiteUrl
        business.updatedAt = datetime.utcnow()
    else:
        business = models.BusinessProfile(
            userId=user_id,
            businessName=b.businessName,
            objective=b.objective,
            websiteUrl=b.websiteUrl,
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow()
        )
        db.add(business)

    await db.commit()
    await db.refresh(business)
    return business