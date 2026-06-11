import os
import secrets
import httpx
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError

log = logging.getLogger("api.auth")

router = APIRouter()

CLIENT_ID = os.environ.get("CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "changeme-secret-key-123")
ALGORITHM = "HS256"
SESSION_EXPIRE_HOURS = 24

DISCORD_API = "https://discord.com/api/v10"


def create_jwt(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRE_HOURS)
    data.update({"exp": expire})
    return jwt.encode(data, API_SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, API_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_jwt(token)


@router.get("/api/auth/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    # Store state in DB
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO oauth_states (state) VALUES ($1) ON CONFLICT DO NOTHING", state
            )
    except Exception:
        pass

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }
    auth_url = "https://discord.com/api/oauth2/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(auth_url)


@router.get("/api/auth/callback")
async def callback(request: Request, response: Response, code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse("/")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Validate state
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state FROM oauth_states WHERE state=$1", state)
            if row:
                await conn.execute("DELETE FROM oauth_states WHERE state=$1", state)
            else:
                raise HTTPException(status_code=400, detail="Invalid state")
    except HTTPException:
        raise
    except Exception:
        pass

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code")

        token_data = token_resp.json()
        access_token = token_data["access_token"]

        user_resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_data = user_resp.json()

    session_data = {
        "user_id": user_data["id"],
        "username": user_data["username"],
        "discriminator": user_data.get("discriminator", "0"),
        "avatar": user_data.get("avatar"),
        "access_token": access_token,
    }
    token = create_jwt(session_data)
    resp = RedirectResponse("/api/dashboard")
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=SESSION_EXPIRE_HOURS * 3600)
    return resp


@router.get("/api/auth/logout")
async def logout():
    resp = RedirectResponse("/")
    resp.delete_cookie("session")
    return resp


@router.get("/api/auth/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "discriminator": user.get("discriminator"),
        "avatar": user.get("avatar"),
    }
