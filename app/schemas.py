from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any, Literal
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


# -------------------------
# Dashboard Schemas
# -------------------------

class DashboardStat(BaseModel):
    id: str
    title: str
    value: str
    change: str
    trend: str


class DashboardCampaign(BaseModel):
    name: str
    status: str
    spend: str
    roi: str
    performance: str
    message: Optional[str] = None


class DashboardNotification(BaseModel):
    id: int
    type: str
    message: str
    time: str


class DashboardRecommendation(BaseModel):
    id: int
    title: str
    description: str
    status: str
    campaign: str
    action: str
    impact: str


class DashboardMetaInfo(BaseModel):
    connected: bool
    selectedAdAccount: Optional[str]
    adAccountCount: int


class DashboardBusinessSummary(BaseModel):
    businessName: Optional[str]
    objective: Optional[str]
    websiteUrl: Optional[str]


class DashboardResponse(BaseModel):
    stats: List[DashboardStat]
    campaigns: List[DashboardCampaign]
    notifications: List[DashboardNotification]
    aiRecommendations: List[DashboardRecommendation]
    meta: DashboardMetaInfo
    business: DashboardBusinessSummary
    generatedAt: datetime


class RecommendationStatusUpdate(BaseModel):
    status: Literal["pending", "approved", "rejected", "applied"]