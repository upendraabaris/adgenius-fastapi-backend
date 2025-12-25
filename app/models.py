from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey,
    TIMESTAMP, text,DateTime
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
    createdAt = Column("createdAt", DateTime(timezone=True), server_default=func.now())  # Default to current timestamp
    updatedAt = Column("updatedAt", DateTime(timezone=True), server_default=func.now(), onupdate=func.now())  # Auto-update on modification

    # business = relationship("Business", back_populates="owner", uselist=False)
    # integrations = relationship("Integration", back_populates="owner")


class BusinessProfile(Base):
    __tablename__ = "Businesses"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"))
    businessName = Column(String(255))
    objective = Column(String(255))
    websiteUrl = Column(String(255))
    createdAt = Column(TIMESTAMP(timezone=True), nullable=False)
    updatedAt = Column(TIMESTAMP(timezone=True), nullable=False)

    # owner = relationship("User", back_populates="business")


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

    # owner = relationship("Users", back_populates="integrations")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('Users.id', ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    message_type = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    extra_data = Column("metadata", JSONB, default={})  # Use column name mapping
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
