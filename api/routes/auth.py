import os
import json
import secrets
import httpx
import logging
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

log = logging.getLogger("api.auth")

router = APIRouter()

SESSION_EXPIRE_HOURS = 24 * 7
DISCORD_API = "https://discord.com/api/v10"
COOKIE_NAME = "np_sid"


# ── DB session helpers ────────────────────────────────────────────

async def _create_session(data: dict) -> str:
    """Store session data in PostgreSQL, return a random session ID."""
    from bot.core.database import get_pool
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRE_HOURS)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, data, expires_at) VALUES ($1, $2::jsonb, $3)",
            session_id, json.dumps(data), expires_at
        )
    return session_id


async def _get_session(session_id: str) -> dict | None:
    """Look up a session. Returns None if not found or expired."""
    if not session_id:
        return None
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data, expires_at FROM sessions WHERE session_id = $1",
                session_id
            )
        if not row:
            return None
        if row["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            await _delete_session(session_id)
            return None
        return json.loads(row["data"])
    except Exception as e:
        log.error(f"Session lookup error: {e}")
        return None


async def _delete_session(session_id: str):
    """Remove a session from the database."""
    if not session_id:
        return
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE session_id = $1", session_id)
    except Exception as e:
        log.warning(f"Session delete error: {e}")


async def get_current_user(request: Request) -> dict | None:
    """Read the session cookie and return session data, or None if not logged in."""
    session_id = request.cookies.get(COOKIE_NAME)
    return await _get_session(session_id)


# ── Cookie helper ─────────────────────────────────────────────────

def _set_session_cookie(response, session_id: str):
    https = _behind_https()
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        secure=https,
        max_age=SESSION_EXPIRE_HOURS * 3600,
        path="/",
    )


def _clear_session_cookie(response):
    https = _behind_https()
    response.delete_cookie(COOKIE_NAME, samesite="lax", secure=https, path="/")


# ── URL / HTTPS helpers ───────────────────────────────────────────

def _build_redirect_uri(request: Request) -> str:
    explicit = os.environ.get("REDIRECT_URI", "").strip()
    if explicit:
        return explicit

    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if replit_domain:
        return f"https://{replit_domain}/api/auth/callback"

    fwd_host  = request.headers.get("x-forwarded-host", "").strip()
    fwd_proto = request.headers.get("x-forwarded-proto", "").strip()
    raw_netloc = request.url.netloc
    host   = fwd_host or raw_netloc.split(":")[0]
    scheme = fwd_proto or ("https" if os.environ.get("RENDER") or os.environ.get("REPLIT_DOMAINS") else "http")
    return f"{scheme}://{host}/api/auth/callback"


def _behind_https() -> bool:
    return bool(
        os.environ.get("RENDER")
        or os.environ.get("REPLIT_DOMAINS")
        or os.environ.get("REPLIT_DEV_DOMAIN")
    )


def _cfg(request: Request = None):
    return {
        "client_id":     os.environ.get("CLIENT_ID", ""),
        "client_secret": os.environ.get("CLIENT_SECRET", ""),
        "redirect_uri":  _build_redirect_uri(request) if request else os.environ.get("REDIRECT_URI", ""),
        "dashboard_url": os.environ.get("DASHBOARD_URL", "").rstrip("/"),
    }


# ── Debug endpoint ────────────────────────────────────────────────
@router.get("/api/auth/debug")
async def debug_config(request: Request):
    cfg = _cfg(request)
    session_id = request.cookies.get(COOKIE_NAME, "")
    session_data = await _get_session(session_id) if session_id else None
    return {
        "client_id_set":      bool(cfg["client_id"]),
        "client_secret_set":  bool(cfg["client_secret"]),
        "redirect_uri":       cfg["redirect_uri"] or "(not set)",
        "redirect_uri_source": (
            "env:REDIRECT_URI" if os.environ.get("REDIRECT_URI") else
            "env:REPLIT_DEV_DOMAIN" if os.environ.get("REPLIT_DEV_DOMAIN") else
            "x-forwarded-host" if request.headers.get("x-forwarded-host") else
            "host-header"
        ),
        "dashboard_url":      cfg["dashboard_url"] or "(not set)",
        "host_header":        request.url.netloc,
        "x_forwarded_host":   request.headers.get("x-forwarded-host", "(not set)"),
        "x_forwarded_proto":  request.headers.get("x-forwarded-proto", "(not set)"),
        "behind_https":       _behind_https(),
        "session_cookie_set": bool(session_id),
        "session_valid":      bool(session_data),
        "session_user":       session_data.get("username") if session_data else None,
    }


# ── Login ─────────────────────────────────────────────────────────
@router.get("/api/auth/login")
async def login(request: Request):
    cfg = _cfg(request)

    if not cfg["client_id"] or not cfg["client_secret"]:
        return RedirectResponse("/?auth_error=no_credentials")

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
        "client_id":     cfg["client_id"],
        "redirect_uri":  cfg["redirect_uri"],
        "response_type": "code",
        "scope":         "identify guilds",
        "state":         state,
    })
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{params}")


# ── Callback ──────────────────────────────────────────────────────
@router.get("/api/auth/callback")
async def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    cfg = _cfg(request)
    dashboard_url = cfg["dashboard_url"]
    guilds_page   = f"{dashboard_url}/guilds" if dashboard_url else "/guilds"
    error_page    = f"{dashboard_url}/?auth_error=1" if dashboard_url else "/?auth_error=1"

    if error:
        log.warning(f"Discord returned OAuth error: {error}")
        return RedirectResponse(error_page)

    if not code or not state:
        return RedirectResponse(error_page)

    # Validate state (best-effort)
    from bot.core.database import get_pool
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state FROM oauth_states WHERE state=$1", state)
            if row:
                await conn.execute("DELETE FROM oauth_states WHERE state=$1", state)
            else:
                log.warning("OAuth state not found — possible replay or DB miss")
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
                return RedirectResponse(f"{dashboard_url}/?auth_error=token_exchange" if dashboard_url else "/?auth_error=token_exchange")

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

            guilds_resp = await client.get(
                f"{DISCORD_API}/users/@me/guilds",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            guilds = guilds_resp.json() if guilds_resp.status_code == 200 else []

    except Exception as e:
        log.error(f"OAuth callback exception: {e}")
        return RedirectResponse(error_page)

    # Filter guilds where user has Manage Guild or Administrator
    MANAGE_GUILD = 0x20
    ADMINISTRATOR = 0x8
    managed_guilds = [
        g for g in guilds
        if isinstance(g.get("permissions"), str) and (
            int(g["permissions"]) & MANAGE_GUILD or int(g["permissions"]) & ADMINISTRATOR
        )
    ]

    session_data = {
        "user_id":       user_data["id"],
        "username":      user_data.get("global_name") or user_data["username"],
        "discriminator": user_data.get("discriminator", "0"),
        "avatar":        user_data.get("avatar"),
        "access_token":  access_token,
        "guilds":        managed_guilds,
    }

    try:
        session_id = await _create_session(session_data)
    except Exception as e:
        log.error(f"Failed to create session: {e}")
        return RedirectResponse(error_page)

    log.info(f"Login success for {user_data['username']} ({user_data['id']})")

    resp = RedirectResponse(guilds_page, status_code=302)
    _set_session_cookie(resp, session_id)
    return resp


# ── Logout ────────────────────────────────────────────────────────
@router.get("/api/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        await _delete_session(session_id)
    cfg = _cfg(request)
    home = cfg["dashboard_url"] or "/"
    resp = RedirectResponse(home, status_code=302)
    _clear_session_cookie(resp)
    return resp


# ── Me ────────────────────────────────────────────────────────────
@router.get("/api/auth/me")
async def me(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "user_id":       user.get("user_id"),
        "username":      user.get("username"),
        "discriminator": user.get("discriminator"),
        "avatar":        user.get("avatar"),
    }


# ── Guilds (from session) ─────────────────────────────────────────
@router.get("/api/auth/guilds")
async def auth_guilds(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.get("guilds", [])
