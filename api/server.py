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
    app = FastAPI(title="Nightpigeon API", docs_url=None, redoc_url=None)

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if "*" in allowed_origins:
        allowed_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
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

    return app
