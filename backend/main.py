"""
FastAPI entry-point for the Autonomous Data Scientist Agent.

Responsibilities
- Mount API routers (auth, chat, upload – added in later chunks)
- Serve the frontend as static files
- Configure CORS for local development
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

class CacheMiddleware(BaseHTTPMiddleware):
    """Add cache headers for static assets."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Cache static assets for 1 hour
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
            response.headers["ETag"] = f'"{hash(request.url.path)}"'

        return response

from backend.config import get_settings
from backend.logging_config import setup_logging
from backend.middleware.request_tracking import RequestTrackingMiddleware
from backend.routes.auth import router as auth_router
from backend.routes.upload import router as upload_router
from backend.routes.chat import router as chat_router

# Initialize logging
setup_logging()

# ── App instance ────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title=settings.APP_TITLE,
    version="0.1.0",
    description="Autonomous AI Agent for data analysis, RAG, web search & code execution.",
)

# ── Middleware ──────────────────────────────────────────────
# Add request tracking middleware (should be added last for proper ordering)
app.add_middleware(RequestTrackingMiddleware)
app.add_middleware(CacheMiddleware)

# ── CORS (restrictive for security) ─────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",  # For development
        "https://your-domain.com",  # Replace with your actual domain
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # 24 hours
)

# ── API Routers ─────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)


# ── Config endpoint ───────────────────────────────────
@app.get("/api/config")
async def get_public_config():
    """Return public (non-secret) frontend configuration."""
    return {
        "supabase_url": settings.SUPABASE_URL,
    }


# ── Static files and root endpoint ──────────────────────
# Mount frontend directory
# Make sure to create a 'static' directory in your 'frontend' folder
frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def serve_index():
    """Serve the login page as the default landing page."""
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/signup.html")
async def serve_signup():
    """Serve the signup page."""
    return FileResponse(str(frontend_dir / "signup.html"))


@app.get("/chat.html")
async def serve_chat():
    """Serve the main chat interface."""
    return FileResponse(str(frontend_dir / "chat.html"))


# ── Health check with dependency status ─────────────────────
@app.get("/api/health")
async def health_check():
    """Comprehensive health check with dependency status."""
    try:
        from backend.services.rag import get_rag_service
        
        rag_service = get_rag_service()
        rag_ready = rag_service.vectorstore is not None or rag_service._initialized
        
        # Check dependencies
        dependencies = {
            "rag_service": rag_ready,
            "uploads_dir": os.path.exists(settings.UPLOAD_DIR),
            "groq_api": bool(settings.GROQ_API_KEY),
            "supabase_config": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
        }
        
        all_healthy = all(dependencies.values())
        
        return JSONResponse(
            status_code=200 if all_healthy else 503,
            content={
                "status": "healthy" if all_healthy else "degraded",
                "app": settings.APP_TITLE,
                "version": "0.1.0",
                "dependencies": dependencies,
            },
        )
    except Exception as e:
        import logging
        logging.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)[:100],
            },
        )


@app.get("/api/health/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    return {"ready": True}
