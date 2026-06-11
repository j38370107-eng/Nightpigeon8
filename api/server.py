import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from api.routes.auth import router as auth_router
from api.routes.config import router as config_router
from api.routes.cases import router as cases_router

log = logging.getLogger("api.server")

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def create_app(bot=None, serve_dashboard: bool = True) -> FastAPI:
    app = FastAPI(title="Nightpigeon API", docs_url=None, redoc_url=None, redirect_slashes=False)

    # Build the allowed-origins list.
    # Browsers reject Access-Control-Allow-Origin: * when credentials are included,
    # so we must enumerate real origins when a cross-domain dashboard is configured.
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    origins: list[str] = [o.strip() for o in raw.split(",") if o.strip()] if raw else []

    # Always include the dashboard origin so the two-service Render setup works.
    dashboard_origin = os.environ.get("DASHBOARD_URL", "").rstrip("/").strip()
    if dashboard_origin and dashboard_origin not in origins:
        origins.append(dashboard_origin)

    # Also include the Replit dev domain when present.
    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if replit_domain:
        replit_origin = f"https://{replit_domain}"
        if replit_origin not in origins:
            origins.append(replit_origin)

    # If no origins were resolved, fall back to permissive wildcard
    # (same-domain deployments don't need explicit CORS).
    allow_credentials = bool(origins)
    if not origins:
        origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if bot:
        app.state.bot = bot

    app.include_router(auth_router)
    app.include_router(config_router)
    app.include_router(cases_router)

    @app.api_route("/ping", methods=["GET", "HEAD"])
    async def ping():
        return Response(content="pong", media_type="text/plain")

    @app.get("/api/healthz")
    async def healthz():
        return {"status": "ok"}

    if serve_dashboard and DASHBOARD_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

        @app.get("/config.js")
        async def config_js():
            return Response(content="window.API_BASE = '';\n", media_type="application/javascript")

        @app.api_route("/", methods=["GET", "HEAD"])
        async def root():
            return FileResponse(str(DASHBOARD_DIR / "index.html"))

        @app.api_route("/guilds", methods=["GET", "HEAD"])
        async def guilds_page():
            return FileResponse(str(DASHBOARD_DIR / "guilds.html"))

        @app.api_route("/api/dashboard", methods=["GET", "HEAD"])
        async def dashboard_redirect():
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/guilds")

        @app.api_route("/config", methods=["GET", "HEAD"])
        async def config_page():
            return FileResponse(str(DASHBOARD_DIR / "config.html"))

        @app.api_route("/cases", methods=["GET", "HEAD"])
        async def cases_page():
            return FileResponse(str(DASHBOARD_DIR / "cases.html"))

        @app.api_route("/docs-page", methods=["GET", "HEAD"])
        async def docs_page():
            return FileResponse(str(DASHBOARD_DIR / "docs.html"))

        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
        async def catch_all(full_path: str):
            if full_path.startswith("api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(str(DASHBOARD_DIR / "index.html"))

    return app
