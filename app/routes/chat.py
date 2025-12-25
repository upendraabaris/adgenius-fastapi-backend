from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import Optional
from uuid import UUID
import uuid
import asyncio

from app.db import AsyncSessionLocal
from app import models
from app.schemas import ChatRequest, ChatResponse, ChatHistoryResponse
from app.mcp_utils import create_user_agent, prewarm_user_agent

router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _require_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return int(user_id)


@router.post("/", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(request)

    # Use existing session_id or create new one
    session_id = req.session_id or uuid.uuid4()

    # Save user message to database
    user_message = models.ChatHistory(
        user_id=user_id,
        session_id=session_id,
        message_type="user",
        content=req.message,
        extra_data={}
    )
    db.add(user_message)
    await db.flush()  # Get the ID without committing
    await db.refresh(user_message)

    # Load this user's Meta integration (must have selected_ad_account)
    result = await db.execute(
        select(models.Integration).where(
            models.Integration.user_id == user_id,
            models.Integration.provider == "meta",
        )
    )
    integration = result.scalars().first()

    # If user is not connected to any Meta account, return a friendly guidance message
    if not integration:
        guidance = (
            "It looks like you don't have a Meta Ads account connected yet. "
            "Please go to the Settings page, connect your Meta Ads account under "
            "\"Connected Accounts\", and then come back here to ask questions "
            "about your campaigns."
        )
        
        # Save assistant response
        assistant_message = models.ChatHistory(
            user_id=user_id,
            session_id=session_id,
            message_type="assistant",
            content=guidance,
            extra_data={"error": "no_meta_integration"}
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            success=False,
            reply=guidance,
            session_id=session_id,
            message_id=assistant_message.id,
            user_message_id=user_message.id
        )

    # If integration exists but no primary ad account is selected
    if not integration.selected_ad_account:
        guidance = (
            "You are connected to Meta, but no primary ad account is selected yet. "
            "Please open the Settings page, use the \"Select/Change Account\" option "
            "under Meta Ads in Connected Accounts, choose an ad account, and then "
            "return to this chat to ask about your performance."
        )
        
        # Save assistant response
        assistant_message = models.ChatHistory(
            user_id=user_id,
            session_id=session_id,
            message_type="assistant",
            content=guidance,
            extra_data={"error": "no_selected_ad_account"}
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            success=False,
            reply=guidance,
            session_id=session_id,
            message_id=assistant_message.id,
            user_message_id=user_message.id
        )

    access_token = integration.access_token
    ad_account_id = integration.selected_ad_account

    # Remove pre-warming for now to avoid issues
    # asyncio.create_task(prewarm_user_agent(user_id, access_token))

    # Get recent chat history for context (last 10 messages from this session)
    history_result = await db.execute(
        select(models.ChatHistory)
        .where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.session_id == session_id,
            models.ChatHistory.id < user_message.id  # Don't include current user message
        )
        .order_by(desc(models.ChatHistory.created_at))
        .limit(10)
    )
    chat_history = history_result.scalars().all()
    
    # Build context from chat history
    context_messages = []
    for msg in reversed(chat_history):  # Reverse to get chronological order
        context_messages.append(f"{msg.message_type.title()}: {msg.content}")
    
    context = "\n".join(context_messages) if context_messages else ""

    # Build or reuse user-specific MCP agent (cached per user_id)
    agent = await create_user_agent(user_id, access_token)

    # Give the agent explicit context about which ad account to use and chat history
    prompt_parts = [
        f"You are connected to Meta Ads for this user.",
        f"The primary ad account id to use is: {ad_account_id}."
    ]
    
    if context:
        prompt_parts.append(f"Previous conversation context:\n{context}")
    
    prompt_parts.append(f"Current question: {req.message}")
    
    prompt = "\n\n".join(prompt_parts)

    try:
        out = await agent.run(prompt)
        
        # Save assistant response
        assistant_message = models.ChatHistory(
            user_id=user_id,
            session_id=session_id,
            message_type="assistant",
            content=out,
            extra_data={"ad_account_id": ad_account_id}
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            success=True,
            reply=out,
            session_id=session_id,
            message_id=assistant_message.id,
            user_message_id=user_message.id
        )
        
    except Exception as e:
        error_msg = f"Sorry, I encountered an error while processing your request: {str(e)}"
        
        # Save error response
        assistant_message = models.ChatHistory(
            user_id=user_id,
            session_id=session_id,
            message_type="assistant",
            content=error_msg,
            extra_data={"error": str(e)}
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            success=False,
            reply=error_msg,
            session_id=session_id,
            message_id=assistant_message.id,
            user_message_id=user_message.id
        )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    request: Request,
    session_id: Optional[UUID] = Query(None, description="Session ID to get history for"),
    limit: int = Query(50, description="Number of messages to retrieve"),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a user. If session_id is provided, get history for that session only."""
    user_id = _require_user_id(request)

    query = select(models.ChatHistory).where(models.ChatHistory.user_id == user_id)
    
    if session_id:
        query = query.where(models.ChatHistory.session_id == session_id)
    
    query = query.order_by(desc(models.ChatHistory.created_at)).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    # Reverse to get chronological order (oldest first)
    messages = list(reversed(messages))
    
    # Get session_id from first message or use provided session_id
    response_session_id = session_id or (messages[0].session_id if messages else uuid.uuid4())
    
    return ChatHistoryResponse(
        messages=messages,
        session_id=response_session_id,
        total_messages=len(messages)
    )


@router.get("/sessions")
async def get_chat_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get all chat sessions for a user with the latest message from each session."""
    user_id = _require_user_id(request)
    
    # Get distinct sessions with their latest message
    result = await db.execute(
        select(models.ChatHistory.session_id, models.ChatHistory.created_at, models.ChatHistory.content)
        .where(models.ChatHistory.user_id == user_id)
        .order_by(models.ChatHistory.session_id, desc(models.ChatHistory.created_at))
        .distinct(models.ChatHistory.session_id)
    )
    
    sessions = []
    for session_id, created_at, latest_content in result:
        sessions.append({
            "session_id": session_id,
            "last_message_at": created_at,
            "latest_content": latest_content[:100] + "..." if len(latest_content) > 100 else latest_content
        })
    
    # Sort by latest message time (most recent first)
    sessions.sort(key=lambda x: x["last_message_at"], reverse=True)
    
    return {"sessions": sessions}

@router.delete("/session/{session_id}")
async def delete_chat_session(
    session_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a complete chat session and all its messages."""
    user_id = _require_user_id(request)
    
    # Check if session exists and belongs to user
    result = await db.execute(
        select(models.ChatHistory)
        .where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.session_id == session_id
        )
        .limit(1)
    )
    
    session_exists = result.scalars().first()
    if not session_exists:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Delete all messages in this session
    await db.execute(
        models.ChatHistory.__table__.delete().where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.session_id == session_id
        )
    )
    
    await db.commit()
    
    return {"success": True, "message": "Chat session deleted successfully"}


@router.delete("/message/{message_id}")
async def delete_chat_message(
    message_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific chat message."""
    user_id = _require_user_id(request)
    
    # Check if message exists and belongs to user
    result = await db.execute(
        select(models.ChatHistory)
        .where(
            models.ChatHistory.id == message_id,
            models.ChatHistory.user_id == user_id
        )
    )
    
    message = result.scalars().first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Delete the message
    await db.delete(message)
    await db.commit()
    
    return {"success": True, "message": "Message deleted successfully"}


@router.delete("/all")
async def delete_all_chats(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete all chat history for the user."""
    user_id = _require_user_id(request)
    
    # Delete all messages for this user
    await db.execute(
        models.ChatHistory.__table__.delete().where(
            models.ChatHistory.user_id == user_id
        )
    )
    
    await db.commit()
    
    return {"success": True, "message": "All chat history deleted successfully"}