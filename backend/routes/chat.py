"""
Chat API Route - Hardened version
Receives user messages, orchestrates the response (LangChain agent),
and returns the AI's reply.
"""

import asyncio
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from backend.services.agent import run_agent
from backend.utils.validators import (
    validate_message,
    validate_session_id,
    validate_title,
    ValidationError,
)
from backend.logging_config import logger_chat, logger_db
from supabase import create_client, ClientOptions
from backend.config import get_settings

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    file_context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    steps: Optional[List[Dict[str, Any]]] = None


class RenameRequest(BaseModel):
    title: str


class SessionItem(BaseModel):
    id: str
    title: str
    last_message: Optional[str] = None
    updated_at: str


class SessionsResponse(BaseModel):
    sessions: List[SessionItem]


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    history: List[MessageItem]


def get_auth_data(request: Request) -> tuple:
    """
    Extract user_id from Supabase JWT token and return an Authenticated Client instance.
    Sanitizes error messages to prevent info leakage.
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        logger_chat.warning("Missing or invalid authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ", 1)[1]
    
    settings = get_settings()
    sb = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )
    
    try:
        user_response = sb.auth.get_user(token)
        if not user_response or not user_response.user:
            logger_chat.warning("Invalid token provided")
            raise HTTPException(status_code=401, detail="Invalid token")
        return sb, str(user_response.user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger_chat.error(f"Auth error: {type(e).__name__}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def generate_title_async(sb, session_id: str, user_msg: str, user_id: str):
    """
    Asynchronous background task to generate smart title without blocking UI.
    Uses Groq Llama for title generation (free tier available).
    """
    try:
        from langchain_groq import ChatGroq

        settings = get_settings()
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=settings.GROQ_API_KEY,
            temperature=0.3,
        )
        title = (
            llm.invoke(
                f"Generate a very short chat title (3-5 words max) for this message: {user_msg[:200]}. Reply with ONLY the title, no quotes or extra text."
            )
            .content.strip()
            .replace('"', "")[:40]
        )
        sb.table("chat_sessions").update({"title": title}).eq("id", session_id).eq(
            "user_id", user_id
        ).execute()
        logger_chat.info(f"Title generated for session {session_id}")
    except Exception as e:
        logger_chat.error(f"Title generation failed for session {session_id}: {e}")


@router.get("/sessions", response_model=SessionsResponse)
async def get_chat_sessions(auth_data: tuple = Depends(get_auth_data)):
    """Fetch all active chat sessions sorted by newest."""
    sb, user_id = auth_data
    try:
        res = (
            sb.table("chat_sessions")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_deleted", False)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        sessions = [SessionItem(**row) for row in res.data]
        logger_chat.info(f"Fetched {len(sessions)} sessions for user {user_id}")
        return SessionsResponse(sessions=sessions)
    except Exception as exc:
        logger_db.error(f"Error fetching sessions: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch sessions")


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    auth_data: tuple = Depends(get_auth_data),
):
    """Paginated load of historical chat messages for a session."""
    sb, user_id = auth_data
    try:
        # Validate session_id format
        try:
            validate_session_id(session_id)
        except ValidationError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        # Verify ownership and non-deletion
        val = (
            sb.table("chat_sessions")
            .select("id")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .eq("is_deleted", False)
            .execute()
        )
        if not val.data:
            logger_chat.warning(
                f"Unauthorized or deleted session access attempt: {session_id}"
            )
            return ChatHistoryResponse(history=[])

        # Fetch messages with safe limits
        limit = min(limit, 100)  # Cap at 100 messages per request
        offset = max(0, offset)
        res = (
            sb.table("chat_messages")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute()
        )
        history = [MessageItem(**row) for row in res.data]
        logger_chat.info(
            f"Fetched {len(history)} messages for session {session_id}"
        )
        return ChatHistoryResponse(history=history)
    except HTTPException:
        raise
    except Exception as exc:
        logger_db.error(f"Error fetching history: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")


@router.post("", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest, auth_data: tuple = Depends(get_auth_data)):
    """Process user message and return AI response."""
    sb, user_id = auth_data

    # Validate input
    try:
        user_msg = validate_message(payload.message)
    except ValidationError as ve:
        logger_chat.warning(f"Invalid message from user {user_id}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    # Validate session_id if provided
    if payload.session_id:
        try:
            validate_session_id(payload.session_id)
        except ValidationError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    try:
        is_new_session = False
        session_id = payload.session_id

        if not session_id:
            # Create new session
            try:
                sess_res = sb.table("chat_sessions").insert(
                    {
                        "user_id": user_id,
                        "title": "New Chat",
                        "last_message": user_msg[:100],
                    }
                ).execute()
                session_id = sess_res.data[0]["id"]
                is_new_session = True
                logger_chat.info(f"New session created: {session_id}")
            except Exception as e:
                logger_db.error(f"Failed to create session: {e}")
                raise HTTPException(status_code=500, detail="Failed to create session")
        else:
            # Verify ownership and existence
            try:
                check = (
                    sb.table("chat_sessions")
                    .select("title")
                    .eq("id", session_id)
                    .eq("user_id", user_id)
                    .eq("is_deleted", False)
                    .execute()
                )
                if not check.data:
                    logger_chat.warning(
                        f"Unauthorized or deleted session access: {session_id}"
                    )
                    raise HTTPException(
                        status_code=404, detail="Session not found or deleted"
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger_db.error(f"Session check failed: {e}")
                raise HTTPException(status_code=500, detail="Session lookup failed")

        # Fetch chat history for context
        try:
            history_res = (
                sb.table("chat_messages")
                .select("role, content")
                .eq("session_id", session_id)
                .order("created_at")
                .limit(10)
                .execute()
            )
            chat_history = history_res.data
        except Exception as e:
            logger_db.error(f"Failed to fetch history: {e}")
            chat_history = []

        # Persist user message
        try:
            sb.table("chat_messages").insert(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "role": "user",
                    "content": user_msg,
                }
            ).execute()
        except Exception as e:
            logger_db.error(f"Failed to persist user message: {e}")
            raise HTTPException(status_code=500, detail="Failed to save message")

        # Fire async title generation for new sessions
        if is_new_session:
            try:
                asyncio.create_task(generate_title_async(sb, session_id, user_msg, user_id))
            except Exception as e:
                logger_chat.error(f"Failed to queue title generation: {e}")

        # Run agent with fallback
        ai_reply_text = "⚠️ Service temporarily unavailable. Please try again."
        steps = []
        try:
            agent_result = run_agent(
                user_msg, file_context=payload.file_context, chat_history=chat_history
            )
            ai_reply_text = agent_result.get("reply", "")
            steps = agent_result.get("steps", [])
            logger_chat.info(f"Agent response generated for session {session_id}")
        except Exception as e:
            logger_chat.error(f"Agent execution failed: {e}")
            # Use fallback message

        # Persist assistant response
        try:
            sb.table("chat_messages").insert(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "role": "assistant",
                    "content": ai_reply_text,
                }
            ).execute()
        except Exception as e:
            logger_db.error(f"Failed to persist assistant message: {e}")
            raise HTTPException(status_code=500, detail="Failed to save response")

        # Update session metadata
        try:
            last_preview = (
                ai_reply_text[:100]
                + ("..." if len(ai_reply_text) > 100 else "")
            )
            sb.table("chat_sessions").update(
                {
                    "last_message": last_preview,
                }
            ).eq("id", session_id).execute()
        except Exception as e:
            logger_db.error(f"Failed to update session metadata: {e}")

        return ChatResponse(reply=ai_reply_text, session_id=session_id, steps=steps)

    except HTTPException:
        raise
    except Exception as exc:
        logger_chat.error(f"Chat endpoint error: {exc}")
        raise HTTPException(status_code=500, detail="Processing failed")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str, auth_data: tuple = Depends(get_auth_data)
):
    """Soft delete a chat session."""
    sb, user_id = auth_data

    # Validate session_id format
    try:
        validate_session_id(session_id)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        result = (
            sb.table("chat_sessions")
            .update({"is_deleted": True})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not result.data:
            logger_chat.warning(f"Delete session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger_chat.info(f"Session deleted: {session_id}")
        return {"message": "Session securely deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger_db.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")


@router.put("/sessions/{session_id}")
async def rename_session(
    session_id: str, payload: RenameRequest, auth_data: tuple = Depends(get_auth_data)
):
    """Rename a chat session."""
    sb, user_id = auth_data

    # Validate inputs
    try:
        validate_session_id(session_id)
        title = validate_title(payload.title)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        result = (
            sb.table("chat_sessions")
            .update({"title": title})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not result.data:
            logger_chat.warning(f"Rename session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger_chat.info(f"Session renamed: {session_id}")
        return {"message": "Session renamed", "title": title}
    except HTTPException:
        raise
    except Exception as e:
        logger_db.error(f"Failed to rename session: {e}")
        raise HTTPException(status_code=500, detail="Failed to rename session")
