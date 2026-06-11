import os
import json
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


def _cfg(request: Request = None):
    return {
        "client_id":     os.environ.get("CLIENT_ID", ""),
        "client_secret": os.environ.get("CLIENT_SECRET", ""),
        "redirect_uri":  _build_redirect_uri(request) if request else os.environ.get("REDIRECT_URI", ""),
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
    # Check Authorization: Bearer <token> header first.
    # This is the primary auth path — the frontend stores the JWT in
    # sessionStorage and sends it as a Bearer token on every request.
    # This completely sidesteps proxy/browser cookie issues.
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        user = decode_jwt(auth[7:])
        if user:
            return user
    # Fall back to cookie (set alongside the sessionStorage token for compat)
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_jwt(token)


def _build_redirect_uri(request: Request) -> str:
    """Build the OAuth redirect URI reliably, handling reverse proxies correctly.
    Priority: REDIRECT_URI env var → Replit domain → X-Forwarded headers → Host header.
    """
    explicit = os.environ.get("REDIRECT_URI", "").strip()
    if explicit:
        return explicit

    # Replit provides its domain as an env var
    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if replit_domain:
        return f"https://{replit_domain}/api/auth/callback"

    # For Render and other proxies: use forwarded headers, not the internal netloc
    # X-Forwarded-Host is the public hostname; X-Forwarded-Proto is the scheme
    fwd_host  = request.headers.get("x-forwarded-host", "").strip()
    fwd_proto = request.headers.get("x-forwarded-proto", "").strip()

    # Strip port from netloc — Render proxies on port 10000 internally
    raw_netloc = request.url.netloc
    host = fwd_host or raw_netloc.split(":")[0]
    scheme = fwd_proto or ("https" if os.environ.get("RENDER") or os.environ.get("REPLIT_DOMAINS") else "http")

    return f"{scheme}://{host}/api/auth/callback"


def _behind_https() -> bool:
    """True when running behind an HTTPS proxy (Render, Replit)."""
    return bool(
        os.environ.get("RENDER")
        or os.environ.get("REPLIT_DOMAINS")
        or os.environ.get("REPLIT_DEV_DOMAIN")
    )


def _set_session_cookie(response, token: str):
    """Set the session cookie.

    Use SameSite=None; Secure only for explicitly cross-domain setups where
    the dashboard lives on a different subdomain from the API (DASHBOARD_URL env
    var is set).  For same-domain deployments (Render single-service, Replit,
    local dev) use SameSite=Lax which is more widely supported — especially on
    iOS Safari which has a known bug rejecting SameSite=None cookies in some
    contexts.
    """
    https = _behind_https()
    is_cross_domain = bool(os.environ.get("DASHBOARD_URL", "").strip())
    samesite = "none" if (https and is_cross_domain) else "lax"
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite=samesite,
        secure=https,
        max_age=SESSION_EXPIRE_HOURS * 3600,
        path="/",
    )


# ── Debug endpoint ───────────────────────────────────────────────
@router.get("/api/auth/debug")
async def debug_config(request: Request):
    cfg = _cfg(request)
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
        "secret_key_set":     cfg["secret_key"] != "changeme-secret-key-123",
        "host_header":        request.url.netloc,
        "x_forwarded_host":   request.headers.get("x-forwarded-host", "(not set)"),
        "x_forwarded_proto":  request.headers.get("x-forwarded-proto", "(not set)"),
        "session_cookie_set": bool(request.cookies.get("session")),
    }


# ── Login ────────────────────────────────────────────────────────
@router.get("/api/auth/login")
async def login(request: Request):
    cfg = _cfg(request)

    if not cfg["client_id"] or not cfg["client_secret"]:
        dashboard_url = cfg["dashboard_url"]
        return RedirectResponse(
            f"{dashboard_url}/?auth_error=no_credentials" if dashboard_url else "/?auth_error=no_credentials"
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
    cfg = _cfg(request)
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
                exchange_error = f"{dashboard_url}/?auth_error=token_exchange" if dashboard_url else "/?auth_error=token_exchange"
                return RedirectResponse(exchange_error)

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

    # Return a 200 HTML page that:
    #  1. Sets the JWT in sessionStorage so the frontend can send it as a
    #     Bearer token — this bypasses ALL cookie proxy/browser issues entirely.
    #  2. Also sets a cookie as a fallback for browsers that block JS storage.
    #  3. Uses a JS redirect (not 302) so the Set-Cookie header is never
    #     stripped by a reverse proxy.
    html = (
        "<!doctype html><html><head>"
        f'<meta http-equiv="refresh" content="0;url={json.dumps(guilds_page)[1:-1]}">'
        "</head><body><script>"
        f"try{{sessionStorage.setItem('np_token',{json.dumps(token)});}}catch(e){{}}"
        f"window.location.replace({json.dumps(guilds_page)});"
        "</script></body></html>"
    )
    resp = HTMLResponse(content=html, status_code=200)
    _set_session_cookie(resp, token)
    return resp


# ── Logout ───────────────────────────────────────────────────────
@router.get("/api/auth/logout")
async def logout(request: Request):
    cfg = _cfg(request)
    home = cfg["dashboard_url"] or "/"
    # Return a 200 HTML page that clears sessionStorage and cookie, then redirects.
    html = (
        "<!doctype html><html><body><script>"
        "try{sessionStorage.removeItem('np_token');}catch(e){}"
        f"window.location.replace({json.dumps(home)});"
        "</script></body></html>"
    )
    resp = HTMLResponse(content=html, status_code=200)
    https = _behind_https()
    is_cross_domain = bool(os.environ.get("DASHBOARD_URL", "").strip())
    samesite = "none" if (https and is_cross_domain) else "lax"
    resp.delete_cookie("session", samesite=samesite, secure=https, path="/")
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
