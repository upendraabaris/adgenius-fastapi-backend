from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey,
    TIMESTAMP, text, DateTime, Boolean
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db import Base
import uuid
from datetime import datetime
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "Users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    email = Column(String(255), unique=True, index=True)
    passwordHash = Column(String(255))
    createdAt = Column("createdAt", DateTime(timezone=True), server_default=func.now())
    updatedAt = Column("updatedAt", DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BusinessProfile(Base):
    __tablename__ = "Businesses"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"))
    businessName = Column(String(255))
    objective = Column(String(255))
    websiteUrl = Column(String(255))
    createdAt = Column(TIMESTAMP(timezone=True), nullable=False)
    updatedAt = Column(TIMESTAMP(timezone=True), nullable=False)


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"))
    provider = Column(Text, nullable=False)
    access_token = Column(Text, nullable=False)
    ad_accounts = Column(JSONB)
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()")
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()")
    )
    selected_ad_account = Column(Text)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    message_type = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    extra_data = Column("metadata", JSONB, default={})
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"), nullable=False)
    plan = Column(String(50), nullable=False)  # 'free_trial', 'read_only', 'write_access'
    status = Column(String(20), nullable=False, default="active")  # 'active', 'expired', 'cancelled'
    razorpay_order_id = Column(String(255))
    razorpay_payment_id = Column(String(255))
    razorpay_signature = Column(String(512))
    amount = Column(Integer)  # in paise
    currency = Column(String(10), default="INR")
    starts_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    expires_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=text("now()"))


class OptimizationHistory(Base):
    __tablename__ = "optimization_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"), nullable=False)
    campaign_id = Column(String(255), nullable=False)
    adset_id = Column(String(255), nullable=False)
    
    # Store JSON snapshots of configurations
    before_config = Column(JSONB, nullable=False)
    after_config = Column(JSONB)
    strategy_tips = Column(JSONB)  # List of tips applied in this batch
    
    status = Column(String(50), default="pending")  # 'applied', 'failed', 'restored', 'pending'
    error_message = Column(Text)
    
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False
    )
