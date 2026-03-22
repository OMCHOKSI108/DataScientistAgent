"""
Streaming chat responses endpoint using Server-Sent Events (SSE).
Allows real-time streaming of agent responses to the client.
"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from backend.services.agent import run_agent
from backend.utils.validators import validate_message, ValidationError
from backend.logging_config import logger_chat
from backend.routes.chat import get_auth_data
from backend.middleware.rate_limiter import rate_limit_chat

router = APIRouter(prefix="/api/chat/stream", tags=["chat"])


class ChatStreamRequest(BaseModel):
    """Streaming chat request."""
    message: str
    file_context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


async def generate_streaming_response(
    user_msg: str,
    session_id: str,
    file_context: Optional[Dict[str, Any]] = None,
    chat_history: Optional[list] = None,
):
    """
    Generate streaming response chunks from the agent.
    Yields JSON-formatted SSE events.
    """
    # Inform client that stream is starting
    yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"

    try:
        # Run agent
        logger_chat.info(f"Streaming chat for session {session_id}")
        agent_result = run_agent(
            user_msg,
            file_context=file_context,
            chat_history=chat_history or []
        )

        reply = agent_result.get("reply", "")
        steps = agent_result.get("steps", [])

        # Emit the full response
        yield f"data: {json.dumps({'type': 'message', 'content': reply})}\n\n"

        # Emit tool steps if any
        if steps:
            for step in steps:
                yield f"data: {json.dumps({'type': 'step', 'tool': step.get('tool'), 'input': step.get('input')})}\n\n"

        # Signal completion
        yield f"data: {json.dumps({'type': 'complete', 'timestamp': datetime.utcnow().isoformat()})}\n\n"

    except Exception as e:
        logger_chat.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:100]})}\n\n"
    finally:
        # Send close signal
        yield f"data: [DONE]\n\n"


@router.post("/chat_stream")
async def chat_stream(
    request: Request,
    payload: ChatStreamRequest,
    auth_data: tuple = Depends(get_auth_data),
):
    """
    Stream chat response in real-time using SSE.
    Client should listen for these event types:
    - start: Stream started
    - message: Agent response text
    - step: Intermediate tool step
    - complete: Stream finished
    - error: Error occurred
    """
    sb, user_id = auth_data
    rate_limit_chat(request, user_id)

    # Validate input
    try:
        user_msg = validate_message(payload.message)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # For now, use a simple session ID or default
    session_id = payload.session_id or f"stream-{user_id}-{int(datetime.utcnow().timestamp())}"

    # Return streaming response
    return StreamingResponse(
        generate_streaming_response(
            user_msg,
            session_id,
            payload.file_context,
            chat_history=None
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
