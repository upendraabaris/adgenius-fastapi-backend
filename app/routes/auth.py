from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db import AsyncSessionLocal
from app import models, schemas
from app.utils import security
from datetime import datetime

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

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
