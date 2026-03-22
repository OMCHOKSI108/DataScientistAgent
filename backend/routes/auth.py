"""
Authentication routes – signup, login, logout via Supabase Auth.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from backend.services.supabase_client import get_supabase_client
from backend.middleware.rate_limiter import rate_limit_auth, rate_limit_global_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ──────────────────────────────

class AuthRequest(BaseModel):
    """Email + password payload for login and signup."""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Successful auth response returned to the client."""
    message: str
    access_token: str | None = None
    user_id: str | None = None
    email: str | None = None


# ── Endpoints ───────────────────────────────────────────────

@router.post("/signup", response_model=AuthResponse)
async def signup(request: Request, payload: AuthRequest):
    """Register a new user with Supabase Auth."""
    try:
        rate_limit_global_ip(request)
        rate_limit_auth(request)
        sb = get_supabase_client()
        result = sb.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
        })

        # Supabase returns user even if email confirmation is pending
        user = result.user
        session = result.session

        return AuthResponse(
            message="Signup successful. Please check your email to confirm.",
            access_token=session.access_token if session else None,
            user_id=str(user.id) if user else None,
            email=payload.email,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Signup failed")


@router.post("/login", response_model=AuthResponse)
async def login(request: Request, payload: AuthRequest):
    """Authenticate an existing user and return an access token."""
    try:
        rate_limit_global_ip(request)
        rate_limit_auth(request)
        sb = get_supabase_client()
        result = sb.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })

        session = result.session
        user = result.user

        return AuthResponse(
            message="Login successful.",
            access_token=session.access_token if session else None,
            user_id=str(user.id) if user else None,
            email=payload.email,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Login failed")


@router.post("/logout")
async def logout():
    """
    Sign out the current user.
    Note: actual token invalidation is handled client-side by removing
    the stored token.  This endpoint is provided for API completeness
    and future server-side session management.
    """
    try:
        return {"message": "Logged out successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
