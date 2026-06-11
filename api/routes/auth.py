import os
import secrets
import httpx
import logging
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from jose import jwt, JWTError

log = logging.getLogger("api.auth")

router = APIRouter()

ALGORITHM = "HS256"
SESSION_EXPIRE_HOURS = 24
DISCORD_API = "https://discord.com/api/v10"


def _cfg():
    return {
        "client_id":     os.environ.get("CLIENT_ID", ""),
        "client_secret": os.environ.get("CLIENT_SECRET", ""),
        "redirect_uri":  os.environ.get("REDIRECT_URI", ""),
        "secret_key":    os.environ.get("API_SECRET_KEY", "changeme-secret-key-123"),
        "dashboard_url": os.environ.get("DASHBOARD_URL", "").rstrip("/"),
    }


def create_jwt(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRE_HOURS)
    data.update({"exp": expire})
    return jwt.encode(data, _cfg()["secret_key"], algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, _cfg()["secret_key"], algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_jwt(token)


def _set_session_cookie(response, token: str):
    """Always SameSite=None; Secure so the cookie works on both same-domain
    (Replit unified) and cross-domain (Render split) HTTPS deployments."""
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=SESSION_EXPIRE_HOURS * 3600,
    )


# ── Debug endpoint ───────────────────────────────────────────────
@router.get("/api/auth/debug")
async def debug_config():
    cfg = _cfg()
    return {
        "client_id_set":     bool(cfg["client_id"]),
        "client_secret_set": bool(cfg["client_secret"]),
        "redirect_uri":      cfg["redirect_uri"] or "(not set)",
        "dashboard_url":     cfg["dashboard_url"] or "(not set)",
        "secret_key_set":    cfg["secret_key"] != "changeme-secret-key-123",
    }


# ── Login ────────────────────────────────────────────────────────
@router.get("/api/auth/login")
async def login(request: Request):
    cfg = _cfg()

    if not cfg["client_id"]:
        return HTMLResponse(
            "<h2 style='font-family:sans-serif;color:#e74c3c'>⚠️ Discord OAuth not configured</h2>"
            "<p style='font-family:sans-serif'>The <b>CLIENT_ID</b> env var is not set.</p>",
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
    except Exception as e:
        log.warning(f"Could not store OAuth state in DB: {e}")

    params = urlencode({
        "client_id":    cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope":        "identify guilds",
        "state":        state,
    })
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{params}")


# ── Callback ─────────────────────────────────────────────────────
@router.get("/api/auth/callback")
async def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    cfg = _cfg()
    dashboard_url = cfg["dashboard_url"]
    guilds_page   = f"{dashboard_url}/guilds" if dashboard_url else "/guilds"
    error_page    = f"{dashboard_url}/?auth_error=1" if dashboard_url else "/?auth_error=1"

    if error:
        log.warning(f"Discord returned OAuth error: {error}")
        return RedirectResponse(error_page)

    if not code or not state:
        return RedirectResponse(error_page)

    # Validate state (best-effort — skip if DB unavailable)
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM oauth_states WHERE state=$1", state
            )
            if row:
                await conn.execute("DELETE FROM oauth_states WHERE state=$1", state)
            else:
                log.warning("OAuth state not found in DB — possible replay attack or DB miss")
    except Exception as e:
        log.warning(f"DB state check skipped: {e}")

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                f"{DISCORD_API}/oauth2/token",
                data={
                    "client_id":     cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  cfg["redirect_uri"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code != 200:
                log.error(f"Token exchange failed ({token_resp.status_code}): {token_resp.text}")
                return RedirectResponse(error_page)

            token_data   = token_resp.json()
            access_token = token_data["access_token"]

            user_resp = await client.get(
                f"{DISCORD_API}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                log.error(f"Failed to fetch user: {user_resp.text}")
                return RedirectResponse(error_page)

            user_data = user_resp.json()

    except Exception as e:
        log.error(f"OAuth callback exception: {e}")
        return RedirectResponse(error_page)

    session_data = {
        "user_id":       user_data["id"],
        "username":      user_data["username"],
        "discriminator": user_data.get("discriminator", "0"),
        "avatar":        user_data.get("avatar"),
        "access_token":  access_token,
    }
    token = create_jwt(session_data)
    log.info(f"Login success for {user_data['username']} ({user_data['id']})")
    resp = RedirectResponse(guilds_page, status_code=302)
    _set_session_cookie(resp, token)
    return resp


# ── Logout ───────────────────────────────────────────────────────
@router.get("/api/auth/logout")
async def logout():
    cfg = _cfg()
    home = cfg["dashboard_url"] or "/"
    resp = RedirectResponse(home, status_code=302)
    resp.delete_cookie("session", samesite="none", secure=True)
    return resp


# ── Me ───────────────────────────────────────────────────────────
@router.get("/api/auth/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "user_id":       user.get("user_id"),
        "username":      user.get("username"),
        "discriminator": user.get("discriminator"),
        "avatar":        user.get("avatar"),
    }
