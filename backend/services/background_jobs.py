"""
Background job processing for async tasks like PDF indexing, title generation, etc.
Uses asyncio tasks for simple fire-and-forget operations.
"""

import asyncio
import logging
from typing import Callable, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Job registry for monitoring
_job_registry = {}


class BackgroundJob:
    """Represents a background job."""

    def __init__(self, job_id: str, job_type: str, user_id: str):
        self.job_id = job_id
        self.job_type = job_type
        self.user_id = user_id
        self.status = "pending"  # pending, running, completed, failed
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.error = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "user_id": self.user_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
        }


async def run_background_job(
    job_id: str,
    job_type: str,
    user_id: str,
    coroutine: asyncio.coroutine,
) -> BackgroundJob:
    """
    Run a job in the background and track its status.

    Args:
        job_id: Unique job identifier
        job_type: Type of job (e.g., "pdf_indexing", "title_generation")
        user_id: User who initiated the job
        coroutine: Async coroutine to execute

    Returns:
        BackgroundJob instance
    """
    job = BackgroundJob(job_id, job_type, user_id)
    _job_registry[job_id] = job

    try:
        job.status = "running"
        job.started_at = datetime.utcnow()

        logger.info(f"Background job started: {job_id} ({job_type})")

        # Execute the coroutine
        result = await coroutine

        job.status = "completed"
        job.result = str(result)[:500]  # Limit result size
        job.completed_at = datetime.utcnow()

        logger.info(f"Background job completed: {job_id} ({job_type})")

    except Exception as e:
        job.status = "failed"
        job.error = str(e)[:200]
        job.completed_at = datetime.utcnow()

        logger.error(f"Background job failed: {job_id} ({job_type}): {e}")

    return job


def queue_background_job(
    job_type: str,
    user_id: str,
    coroutine: asyncio.coroutine,
) -> str:
    """
    Queue a background job to run asynchronously.

    Args:
        job_type: Type of job
        user_id: User ID
        coroutine: Async coroutine to execute

    Returns:
        Job ID for tracking
    """
    import uuid

    job_id = f"{job_type}_{uuid.uuid4().hex[:8]}"

    # Create task to run in background
    task = asyncio.create_task(
        run_background_job(job_id, job_type, user_id, coroutine)
    )

    # Don't await - let it run in background
    logger.info(f"Background job queued: {job_id} ({job_type})")

    return job_id


def get_job_status(job_id: str) -> Optional[dict]:
    """Get status of a background job."""
    job = _job_registry.get(job_id)
    if job:
        return job.to_dict()
    return None


def cleanup_old_jobs(max_age_hours: int = 24):
    """Remove old completed jobs from registry."""
    now = datetime.utcnow()
    expired_ids = [
        job_id
        for job_id, job in _job_registry.items()
        if (now - job.completed_at).total_seconds() > max_age_hours * 3600
        and job.status in ["completed", "failed"]
    ]

    for job_id in expired_ids:
        del _job_registry[job_id]

    if expired_ids:
        logger.info(f"Cleaned up {len(expired_ids)} old background jobs")


# Specific job types
async def index_pdf_async(
    file_path: str,
    user_id: str,
):
    """Background job for PDF indexing."""
    from backend.services.pdf_loader import load_pdf

    result = load_pdf(file_path)
    return f"Indexed {result.get('filename', 'unknown')} with {len(result.get('chunks', []))} chunks"


async def generate_title_async(
    session_id: str,
    user_msg: str,
    user_id: str,
    sb=None,
):
    """Background job for session title generation using Groq."""
    if not sb:
        from supabase import create_client, ClientOptions
        from backend.config import get_settings

        settings = get_settings()
        sb = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY,
        )

    try:
        from langchain_groq import ChatGroq
        from backend.config import get_settings

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

        return f"Generated title: {title}"

    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        raise


def queue_pdf_indexing(file_path: str, user_id: str) -> str:
    """Queue a PDF indexing job."""
    return queue_background_job(
        "pdf_indexing",
        user_id,
        index_pdf_async(file_path, user_id),
    )


def queue_title_generation(
    session_id: str,
    user_msg: str,
    user_id: str,
) -> str:
    """Queue a title generation job."""
    return queue_background_job(
        "title_generation",
        user_id,
        generate_title_async(session_id, user_msg, user_id),
    )
