import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routes.auth import router as auth_router
from api.routes.config import router as config_router
from api.routes.cases import router as cases_router

log = logging.getLogger("api.server")

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


def create_app(bot=None) -> FastAPI:
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

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    @app.get("/api/healthz")
    async def healthz():
        return {"status": "ok"}

    # Serve dashboard HTML files
    if DASHBOARD_DIR.exists():
        # Static assets
        static_assets = DASHBOARD_DIR
        app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

        @app.get("/")
        async def root():
            return FileResponse(str(DASHBOARD_DIR / "index.html"))

        @app.get("/guilds")
        async def guilds_page():
            return FileResponse(str(DASHBOARD_DIR / "guilds.html"))

        @app.get("/api/dashboard")
        async def dashboard_redirect():
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/guilds")

        @app.get("/config")
        async def config_page():
            return FileResponse(str(DASHBOARD_DIR / "config.html"))

        @app.get("/cases")
        async def cases_page():
            return FileResponse(str(DASHBOARD_DIR / "cases.html"))

        @app.get("/docs-page")
        async def docs_page():
            return FileResponse(str(DASHBOARD_DIR / "docs.html"))

    return app
