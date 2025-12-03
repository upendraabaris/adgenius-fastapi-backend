# import sqlalchemy
# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
# from sqlalchemy.orm import sessionmaker, declarative_base

# from app.config import settings

# DATABASE_URL = settings.DATABASE_URL
# engine = create_async_engine(DATABASE_URL, echo=False, future=True, connect_args={"ssl": False})
# AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# Base = declarative_base()

# async def init_db():
#     # Import models here so they are registered on metadata
#     from app import models
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)


import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from sqlalchemy import text


# Create SSL context (no certificate verification)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    settings.DATABASE_URL,
    future=True,
    echo=False,
    connect_args={"ssl": ssl_context}   # ⬅ SSL enabled but verification disabled
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# async def init_db():
#     from app import models
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.create_all)


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        print("✅ DB connection OK")
    except Exception as e:
        print("❌ DB connection failed:", e)


