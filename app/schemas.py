from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


# -------------------------
# User Schemas
# -------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str]

    class Config:
        from_attributes = True  # Enable from_orm for ORM models


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BusinessCreate(BaseModel):
    businessName: Optional[str] = None
    objective: Optional[str] = None
    websiteUrl: Optional[str] = None


class IntegrationCreate(BaseModel):
    provider: str
    access_token: str
    ad_accounts: Optional[Any] = None
    selected_ad_account: Optional[str] = None

class SignupResponse(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"