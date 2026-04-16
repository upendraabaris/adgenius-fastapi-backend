import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException
from app import models

def estimate_tokens(text: str) -> int:
    """
    Estimate tokens based on character count.
    Standard approximation: 1 token ~= 4 characters.
    Using 3.5 to be conservative and ensure credits cover 10k real tokens.
    """
    if not text:
        return 0
    return math.ceil(len(text) / 3.5)

async def deduct_credits(db: AsyncSession, user_id: int, total_tokens: int):
    """
    Deduct credits based on token count using high-bound ceiling.
    1 credit = 10,000 tokens.
    If 12,000 tokens are used, 2 credits are deducted.
    """
    if total_tokens <= 0:
        return

    # Calculate credits to deduct (Ceiling Logic)
    credits_to_deduct = math.ceil(total_tokens / 10000)

    # Fetch user
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.credits_balance < credits_to_deduct:
        raise HTTPException(
            status_code=402, 
            detail=f"Insufficient credits. This action requires {credits_to_deduct} credits, but you only have {user.credits_balance} left."
        )

    # Deduct and commit
    old_balance = user.credits_balance
    user.credits_balance -= credits_to_deduct
    await db.commit()
    await db.refresh(user)
    
    # DEBUG CONSOLE LOGGING
    print(f"\n{'='*30}")
    print(f"💰 CREDIT DEDUCTION VERIFICATION")
    print(f"👤 User ID: {user_id}")
    print(f"📊 Tokens used: {total_tokens}")
    print(f"➖ Credits deducted: {credits_to_deduct}")
    print(f"🔄 Balance: {old_balance} -> {user.credits_balance}")
    print(f"{'='*30}\n")
    
    return user.credits_balance
