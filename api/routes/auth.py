import os
import secrets
import httpx
import logging
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from jose import jwt, JWTError

log = logging.getLogger("api.auth")

router = APIRouter()

ALGORITHM = "HS256"
SESSION_EXPIRE_HOURS = 24
DISCORD_API = "https://discord.com/api/v10"


def _cfg():
    return {
        "client_id": os.environ.get("CLIENT_ID", ""),
        "client_secret": os.environ.get("CLIENT_SECRET", ""),
        "redirect_uri": os.environ.get("REDIRECT_URI", ""),
        "secret_key": os.environ.get("API_SECRET_KEY", "changeme-secret-key-123"),
        "dashboard_url": os.environ.get("DASHBOARD_URL", "").rstrip("/"),
    }


def create_jwt(data: dict) -> str:
    cfg = _cfg()
    expire = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRE_HOURS)
    data.update({"exp": expire})
    return jwt.encode(data, cfg["secret_key"], algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    cfg = _cfg()
    try:
        return jwt.decode(token, cfg["secret_key"], algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_jwt(token)


def _set_session_cookie(response: RedirectResponse, token: str):
    """Set the session cookie. Uses SameSite=None+Secure for cross-domain (Render split),
    falls back to Lax for same-domain (Replit unified)."""
    dashboard_url = os.environ.get("DASHBOARD_URL", "")
    cross_domain = bool(dashboard_url)
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="none" if cross_domain else "lax",
        secure=cross_domain,
        max_age=SESSION_EXPIRE_HOURS * 3600,
    )


@router.get("/api/auth/login")
async def login(request: Request):
    cfg = _cfg()

    if not cfg["client_id"]:
        return HTMLResponse(
            "<h2 style='font-family:sans-serif;color:#e74c3c'>⚠️ Discord OAuth not configured</h2>"
            "<p style='font-family:sans-serif'>The <b>CLIENT_ID</b> secret is not set. "
            "Add it in your environment variables and restart the app.</p>",
            status_code=503,
        )

    state = secrets.token_urlsafe(32)

    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO oauth_states (state) VALUES ($1) ON CONFLICT DO NOTHING", state
            )
    except Exception:
        pass

    params = urlencode({
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    })
    auth_url = f"https://discord.com/api/oauth2/authorize?{params}"
    return RedirectResponse(auth_url)


@router.get("/api/auth/callback")
async def callback(request: Request, response: Response, code: str = None, state: str = None, error: str = None):
    cfg = _cfg()
    dashboard_url = cfg["dashboard_url"]

    home = dashboard_url or "/"
    guilds_page = f"{dashboard_url}/guilds" if dashboard_url else "/guilds"

    if error:
        return RedirectResponse(home)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

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

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            log.error(f"Token exchange failed: {token_resp.text}")
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
    resp = RedirectResponse(guilds_page)
    _set_session_cookie(resp, token)
    return resp


@router.get("/api/auth/logout")
async def logout(request: Request):
    cfg = _cfg()
    home = cfg["dashboard_url"] or "/"
    resp = RedirectResponse(home)
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
